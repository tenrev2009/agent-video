# 🎬 Video Scene → Kling Prompt Agent

Agent IA qui analyse une vidéo scène par scène (tranches de 15 secondes) et génère,
pour chaque scène, **le meilleur prompt en anglais pour Kling AI** — en mode simple
et en mode **Multi-Shot** — afin de recréer une scène équivalente, avec des
**variations d'environnement, de saison et de style**.

## Ce que fait l'agent

1. **Récupère la vidéo** : fichier local ou URL directe (`.mp4`, `.mov`…).
2. **Découpe en scènes de 15 s** avec ffmpeg et extrait 4 images clés par scène.
3. **Analyse chaque scène** avec Claude (vision) :
   - mouvements détaillés des acteurs (chronologie, gestes, direction, vitesse, expressions) ;
   - environnement (décor, lumière, heure, météo/saison, accessoires) ;
   - caméra (cadrage, angle, mouvement).
4. **Génère les prompts Kling en anglais** :
   - un prompt single-shot optimisé (structure : sujet + mouvement + environnement +
     lumière + caméra + style) ;
   - un negative prompt ;
   - un découpage **Multi-Shot** en 2–4 plans cohérents (mêmes personnages, même
     décor, même lumière — seuls le cadrage et l'action changent) ;
   - 3–4 **variations** : mêmes acteurs et mêmes mouvements, mais nouvel
     environnement, autre saison, autre heure ou autre style visuel.
5. **Produit un rapport** : `kling_prompts.md` (lisible, prompts prêts à coller
   dans Kling) et `kling_prompts.json` (données structurées).

## Installation

```bash
# 1. ffmpeg (obligatoire)
sudo apt install ffmpeg        # Linux
brew install ffmpeg            # macOS

# 2. Dépendances Python
pip install -r requirements.txt

# 3. Clé API Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

## Utilisation

```bash
# Vidéo locale
python video_scene_agent.py ma_video.mp4

# Vidéo depuis une URL directe
python video_scene_agent.py https://exemple.com/clip.mp4

# Tester rapidement sur les 2 premières scènes
python video_scene_agent.py ma_video.mp4 --max-scenes 2

# Options
python video_scene_agent.py ma_video.mp4 \
    --scene-duration 15 \        # durée d'une scène (s)
    --frames-per-scene 4 \       # images clés analysées par scène
    --output mon_rapport/        # dossier de sortie
```

> Pour une vidéo YouTube, téléchargez-la d'abord avec `yt-dlp` puis passez le
> fichier local à l'agent : `yt-dlp -f mp4 <url> -o clip.mp4`.

## Exemple de sortie (extrait)

````markdown
## Scène 2 — 15s → 30s

**Résumé :** Une femme en manteau rouge traverse une place pavée sous la pluie…

### 🎬 Prompt Kling (single shot)
```text
A woman in a long red wool coat walks briskly across a rain-soaked cobblestone
plaza, clutching a black umbrella that tilts against the wind; she glances over
her shoulder mid-stride, her pace quickening... golden streetlamps reflect off
the wet stones, light drizzle, dusk atmosphere. Medium tracking shot, camera
dollies alongside her at eye level. Cinematic, 35mm film, shallow depth of field.
```

### 🌍 Variations
**Version hiver** — même chorégraphie, place enneigée au crépuscule…
````

## Utilisation comme sous-agent Claude Code

Une définition d'agent est fournie dans `.claude/agents/video-scene-kling.md`
(à la racine du dépôt). Dans Claude Code, demandez par exemple :

> « Utilise l'agent video-scene-kling pour analyser clip.mp4 »

## Coût et réglages

- Chaque scène = 1 appel API avec ~4 images → comptez quelques centimes par scène
  avec le modèle par défaut (`claude-opus-4-8`).
- `--frames-per-scene 6` améliore la reconstruction des mouvements rapides
  (coût un peu plus élevé).
- `--max-scenes` permet de valider le résultat avant de lancer une vidéo longue.
