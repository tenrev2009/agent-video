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
4. **Construit une fiche de cohérence des personnages** (si la vidéo a plus d'une
   scène) : un aperçu de toute la vidéo est analysé pour identifier les personnages
   récurrents et figer, pour chacun, une description anglaise fixe — réutilisée mot
   pour mot dans le prompt de chaque scène où ils apparaissent, afin qu'ils restent
   visuellement identiques d'un plan Kling à l'autre.
5. **Génère les prompts Kling en anglais**, pour chaque scène de 15 s de la vidéo :
   - un prompt single-shot optimisé (structure : sujet + mouvement + environnement +
     lumière + caméra + style) ;
   - un negative prompt ;
   - un découpage **Multi-Shot** en 2–4 plans cohérents (mêmes personnages, même
     décor, même lumière — seuls le cadrage et l'action changent) ;
   - 3–4 **variations** : mêmes acteurs et mêmes mouvements, mais nouvel
     environnement, autre saison, autre heure ou autre style visuel.
6. **Produit un rapport** : `kling_prompts.md` (lisible, prompts prêts à coller
   dans Kling) et `kling_prompts.json` (données structurées).

Une vidéo de 2 minutes donne ainsi ~8 scènes de 15 s, chacune avec son propre jeu de
prompts Kling — et les mêmes personnages décrits à l'identique dans chacune.

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
    --bible-frames 12 \          # nb max de scènes échantillonnées pour la fiche personnages
    --no-character-bible \       # désactive la cohérence des personnages entre scènes
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

## Cohérence des personnages entre scènes

Pour une vidéo de plusieurs scènes, l'agent construit d'abord une **fiche
personnages** (un appel API supplémentaire, sur une image par scène) qui identifie
chaque personnage récurrent et fige sa description en anglais :

```markdown
## 🧑 Personnages identifiés (cohérence inter-scènes)

- **homme au manteau bleu marine** (`char_1`) — A tall man in his late 30s with
  short dark hair and stubble, wearing a navy wool peacoat, dark jeans and brown
  leather boots.
```

Cette description est ensuite réutilisée mot pour mot dans le prompt Kling de
chaque scène où ce personnage apparaît (single-shot, Multi-Shot et variations),
pour qu'il reste visuellement le même d'un plan généré à l'autre. Désactivable
avec `--no-character-bible` si vous préférez une analyse indépendante par scène.

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
