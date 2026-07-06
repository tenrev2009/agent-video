#!/usr/bin/env python3
"""
Video Scene → Kling Prompt Agent
================================

Agent IA qui :
  1. Récupère une vidéo (fichier local ou URL directe)
  2. La découpe en scènes de 15 secondes (ffmpeg)
  3. Analyse chaque scène avec Claude (vision) : mouvements des acteurs,
     environnement, caméra, lumière, ambiance
  4. Génère le meilleur prompt en anglais pour Kling AI (mode single-shot
     et mode Multi-Shot) afin de recréer une scène équivalente
  5. Propose des variations : nouvel environnement, autre saison, autre style

Usage :
    export ANTHROPIC_API_KEY=sk-ant-...
    python video_scene_agent.py ma_video.mp4
    python video_scene_agent.py https://exemple.com/video.mp4 --output rapport/
    python video_scene_agent.py ma_video.mp4 --scene-duration 15 --frames-per-scene 4

Prérequis : ffmpeg + ffprobe installés, pip install anthropic
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_SCENE_DURATION = 15.0  # secondes
DEFAULT_FRAMES_PER_SCENE = 4
MAX_FRAME_WIDTH = 1280  # limite la taille des images envoyées à l'API

# ---------------------------------------------------------------------------
# Schéma de sortie structurée : garantit un JSON exploitable pour chaque scène
# ---------------------------------------------------------------------------
SCENE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "scene_summary",
        "actors",
        "environment",
        "camera",
        "kling_prompt",
        "kling_negative_prompt",
        "multishot",
        "variations",
    ],
    "properties": {
        "scene_summary": {
            "type": "string",
            "description": "Résumé de la scène en français (2-3 phrases).",
        },
        "actors": {
            "type": "array",
            "description": "Chaque personne/animal/véhicule en mouvement dans la scène.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["description", "movements"],
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Apparence, vêtements, position dans le cadre (en anglais).",
                    },
                    "movements": {
                        "type": "string",
                        "description": (
                            "Chronologie détaillée des mouvements sur les 15 s "
                            "(gestes, déplacements, direction, vitesse, expressions) en anglais."
                        ),
                    },
                },
            },
        },
        "environment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["setting", "lighting", "time_of_day", "weather_or_season", "key_props"],
            "properties": {
                "setting": {"type": "string", "description": "Lieu et décor, en anglais."},
                "lighting": {"type": "string", "description": "Type et direction de la lumière, en anglais."},
                "time_of_day": {"type": "string"},
                "weather_or_season": {"type": "string"},
                "key_props": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Objets/éléments de décor importants, en anglais.",
                },
            },
        },
        "camera": {
            "type": "object",
            "additionalProperties": False,
            "required": ["shot_type", "angle", "movement"],
            "properties": {
                "shot_type": {"type": "string", "description": "wide shot, medium shot, close-up..."},
                "angle": {"type": "string", "description": "eye level, low angle, high angle, aerial..."},
                "movement": {
                    "type": "string",
                    "description": "static, pan left/right, tilt, dolly in/out, tracking, handheld, crane...",
                },
            },
        },
        "kling_prompt": {
            "type": "string",
            "description": (
                "LE meilleur prompt en anglais pour recréer la scène avec Kling AI en un seul plan. "
                "Structure : subject + detailed subject motion + environment + lighting/atmosphere + "
                "camera shot & movement + visual style. Précis, cinématographique, sans négations."
            ),
        },
        "kling_negative_prompt": {
            "type": "string",
            "description": "Negative prompt Kling en anglais (artefacts à éviter).",
        },
        "multishot": {
            "type": "array",
            "description": (
                "Découpage de la scène en 2 à 4 plans pour le mode Multi-Shot de Kling, "
                "couvrant ensemble les 15 secondes."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["shot_number", "duration_seconds", "prompt"],
                "properties": {
                    "shot_number": {"type": "integer"},
                    "duration_seconds": {"type": "number"},
                    "prompt": {
                        "type": "string",
                        "description": "Prompt Kling en anglais pour ce plan précis, cohérent avec les autres plans.",
                    },
                },
            },
        },
        "variations": {
            "type": "array",
            "description": (
                "3 à 4 variations créatives : mêmes acteurs et mêmes mouvements, mais nouvel "
                "environnement, autre saison, autre heure ou autre style visuel."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "concept", "kling_prompt"],
                "properties": {
                    "name": {"type": "string", "description": "Nom court de la variation, en français."},
                    "concept": {"type": "string", "description": "Ce qui change par rapport à l'original, en français."},
                    "kling_prompt": {
                        "type": "string",
                        "description": "Prompt Kling complet en anglais pour cette variation.",
                    },
                },
            },
        },
    },
}

SYSTEM_PROMPT = """\
You are an expert film analyst and AI-video prompt engineer specialized in Kling AI \
(text-to-video and Multi-Shot mode).

You are given several keyframes sampled in chronological order from ONE scene of about \
15 seconds. Your job:

1. RECONSTRUCT THE MOTION. Compare the frames to infer what happens BETWEEN them: who moves, \
in which direction, at what speed, with which gestures and facial expressions. Describe actor \
movement as a precise timeline — this is the most important part.
2. DESCRIBE THE ENVIRONMENT precisely: location, architecture/nature, props, lighting \
direction and quality, time of day, weather/season, color palette, atmosphere.
3. DESCRIBE THE CAMERA: shot type, angle, and inferred camera movement across the frames.
4. WRITE THE BEST KLING PROMPT (English) to recreate an equivalent scene. Follow Kling best \
practices: one flowing paragraph; structure = subject(s) with visual details + explicit subject \
motion verbs + environment + lighting & atmosphere + camera shot and camera movement + visual \
style (e.g. "cinematic, 35mm film, shallow depth of field"). Be concrete and visual; avoid \
negations, avoid abstract words, keep it under ~1800 characters.
5. WRITE A MULTI-SHOT BREAKDOWN: split the 15-second scene into 2-4 consecutive shots for \
Kling Multi-Shot. Keep characters, wardrobe, environment and light IDENTICAL across shots so \
the shots cut together seamlessly; only the framing, camera move and action beat change.
6. PROPOSE VARIATIONS: 3-4 creative alternatives that keep the same actors and the same \
choreography/movements but transpose the scene — new environment, different season, different \
time of day, or different visual style. Each variation gets its own complete Kling prompt in \
English.

Analysis text fields are in English except where the schema says French \
(scene_summary and variation name/concept are in French for the report).
"""


# ---------------------------------------------------------------------------
# Outils vidéo (ffmpeg / ffprobe)
# ---------------------------------------------------------------------------

def check_dependencies() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"Erreur : `{tool}` est introuvable. Installez ffmpeg (https://ffmpeg.org).")


def download_video(url: str, workdir: Path) -> Path:
    """Télécharge une vidéo depuis une URL directe (mp4, mov...)."""
    dest = workdir / "source_video"
    print(f"→ Téléchargement de {url} ...")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)
    return dest


def get_duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def extract_frame(video: Path, timestamp: float, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{timestamp:.3f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale='min({MAX_FRAME_WIDTH},iw)':-2",
         "-q:v", "3", str(dest)],
        check=True,
    )


@dataclass
class Scene:
    index: int
    start: float
    end: float
    frames: list = field(default_factory=list)  # [(timestamp, Path), ...]


def split_scenes(video: Path, workdir: Path, scene_duration: float,
                 frames_per_scene: int, max_scenes: int | None) -> list[Scene]:
    duration = get_duration(video)
    print(f"→ Durée de la vidéo : {duration:.1f} s")
    scenes: list[Scene] = []
    start = 0.0
    index = 1
    while start < duration - 0.5:
        end = min(start + scene_duration, duration)
        scene = Scene(index=index, start=start, end=end)
        span = end - start
        for i in range(frames_per_scene):
            # échantillonnage réparti sur la scène (léger retrait des bords)
            ts = start + span * (i + 0.5) / frames_per_scene
            frame_path = workdir / f"scene{index:03d}_frame{i + 1}.jpg"
            extract_frame(video, ts, frame_path)
            scene.frames.append((ts, frame_path))
        scenes.append(scene)
        print(f"   Scène {index:02d} [{start:6.1f}s → {end:6.1f}s] : {len(scene.frames)} images extraites")
        index += 1
        start = end
        if max_scenes and len(scenes) >= max_scenes:
            print(f"   (limite --max-scenes={max_scenes} atteinte)")
            break
    return scenes


# ---------------------------------------------------------------------------
# Analyse d'une scène avec Claude (vision + sortie structurée)
# ---------------------------------------------------------------------------

def encode_image(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def analyze_scene(client: anthropic.Anthropic, model: str, scene: Scene) -> dict | None:
    content = [{
        "type": "text",
        "text": (
            f"Scene {scene.index}: from {scene.start:.1f}s to {scene.end:.1f}s of the source "
            f"video. The {len(scene.frames)} keyframes below are in chronological order."
        ),
    }]
    for ts, frame_path in scene.frames:
        content.append({"type": "text", "text": f"Keyframe at t = {ts:.1f}s:"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": encode_image(frame_path),
            },
        })

    with client.messages.stream(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": SCENE_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        print(f"   ⚠ Scène {scene.index} : requête refusée par les classificateurs de sécurité.")
        return None
    if response.stop_reason == "max_tokens":
        print(f"   ⚠ Scène {scene.index} : sortie tronquée (max_tokens atteint).")

    text = "".join(block.text for block in response.content if block.type == "text")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def render_markdown(video_name: str, results: list[tuple[Scene, dict]]) -> str:
    lines = [
        f"# Analyse vidéo & prompts Kling — {video_name}",
        "",
        f"{len(results)} scène(s) de ~15 s analysée(s). "
        "Tous les prompts sont en anglais, prêts à coller dans Kling AI.",
        "",
    ]
    for scene, data in results:
        lines += [
            f"## Scène {scene.index} — {scene.start:.0f}s → {scene.end:.0f}s",
            "",
            f"**Résumé :** {data['scene_summary']}",
            "",
            "### Acteurs et mouvements",
            "",
        ]
        for actor in data["actors"]:
            lines += [f"- **{actor['description']}**", f"  - Mouvements : {actor['movements']}"]
        env = data["environment"]
        cam = data["camera"]
        lines += [
            "",
            "### Environnement",
            "",
            f"- Décor : {env['setting']}",
            f"- Lumière : {env['lighting']}",
            f"- Moment : {env['time_of_day']} — {env['weather_or_season']}",
            f"- Éléments clés : {', '.join(env['key_props']) or '—'}",
            "",
            "### Caméra",
            "",
            f"- Cadrage : {cam['shot_type']} | Angle : {cam['angle']} | Mouvement : {cam['movement']}",
            "",
            "### 🎬 Prompt Kling (single shot)",
            "",
            "```text",
            data["kling_prompt"],
            "```",
            "",
            "**Negative prompt :**",
            "",
            "```text",
            data["kling_negative_prompt"],
            "```",
            "",
            "### 🎞 Multi-Shot Kling",
            "",
        ]
        for shot in data["multishot"]:
            lines += [
                f"**Shot {shot['shot_number']} (~{shot['duration_seconds']:.0f}s)**",
                "",
                "```text",
                shot["prompt"],
                "```",
                "",
            ]
        lines += ["### 🌍 Variations (environnement / saison / style)", ""]
        for var in data["variations"]:
            lines += [
                f"**{var['name']}** — {var['concept']}",
                "",
                "```text",
                var["kling_prompt"],
                "```",
                "",
            ]
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse une vidéo par scènes de 15 s et génère des prompts Kling (EN).")
    parser.add_argument("video", help="Chemin local ou URL directe de la vidéo")
    parser.add_argument("--scene-duration", type=float, default=DEFAULT_SCENE_DURATION,
                        help="Durée d'une scène en secondes (défaut : 15)")
    parser.add_argument("--frames-per-scene", type=int, default=DEFAULT_FRAMES_PER_SCENE,
                        help="Nombre d'images clés analysées par scène (défaut : 4)")
    parser.add_argument("--max-scenes", type=int, default=None,
                        help="Limiter le nombre de scènes analysées (utile pour tester)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Modèle Claude (défaut : {DEFAULT_MODEL})")
    parser.add_argument("--output", default="kling_report",
                        help="Dossier de sortie (défaut : kling_report/)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Note : ANTHROPIC_API_KEY n'est pas défini — le SDK utilisera le profil "
              "`ant auth login` s'il existe.", file=sys.stderr)

    check_dependencies()
    client = anthropic.Anthropic()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kling_agent_") as tmp:
        workdir = Path(tmp)
        if args.video.startswith(("http://", "https://")):
            video = download_video(args.video, workdir)
            video_name = args.video.rsplit("/", 1)[-1] or "video"
        else:
            video = Path(args.video)
            if not video.exists():
                sys.exit(f"Erreur : fichier introuvable : {video}")
            video_name = video.name

        scenes = split_scenes(video, workdir, args.scene_duration,
                              args.frames_per_scene, args.max_scenes)

        results: list[tuple[Scene, dict]] = []
        for scene in scenes:
            print(f"→ Analyse de la scène {scene.index}/{len(scenes)} avec {args.model} ...")
            try:
                data = analyze_scene(client, args.model, scene)
            except anthropic.RateLimitError:
                print(f"   ⚠ Scène {scene.index} : limite de débit atteinte, nouvelle tentative "
                      "gérée par le SDK a échoué — scène ignorée.")
                continue
            except anthropic.APIStatusError as e:
                print(f"   ⚠ Scène {scene.index} : erreur API {e.status_code} — scène ignorée.")
                continue
            if data is not None:
                results.append((scene, data))
                print(f"   ✓ Scène {scene.index} analysée — prompt Kling généré.")

    if not results:
        sys.exit("Aucune scène n'a pu être analysée.")

    json_path = output_dir / "kling_prompts.json"
    md_path = output_dir / "kling_prompts.md"
    json_path.write_text(json.dumps(
        [{"scene": s.index, "start": s.start, "end": s.end, **d} for s, d in results],
        ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(video_name, results), encoding="utf-8")

    print()
    print(f"✅ Terminé : {len(results)} scène(s) analysée(s).")
    print(f"   Rapport lisible : {md_path}")
    print(f"   Données JSON    : {json_path}")


if __name__ == "__main__":
    main()
