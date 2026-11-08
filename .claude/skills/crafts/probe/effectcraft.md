# effectcraft 기능 시험 결과(engine/craft/probe.py)

| 종류 | 결과 | 수 |
|---|---|---|
| command | error | 1 |
| command | needs_context | 146 |
| command | needs_params | 232 |
| command | ok | 319 |
| command | untested | 45 |
| effect | ok | 308 |
| preset | ok | 76 |

## 견본 판(기본값 그대로 · 이미지 · 픽셀 레이어에 적용해 화면이 바뀐 것) — Read 로 본다
- command Composition (1개): `data/workspace/probe/effectcraft/sheets/command_Composition.png`
- command Edit (4개): `data/workspace/probe/effectcraft/sheets/command_Edit.png`
- command File > Replace Footage (2개): `data/workspace/probe/effectcraft/sheets/command_File_Replace_Footage.png`
- command Layer (1개): `data/workspace/probe/effectcraft/sheets/command_Layer.png`
- command Layer > Layer Styles (7개): `data/workspace/probe/effectcraft/sheets/command_Layer_Layer_Styles.png`
- command Layer > Mask (1개): `data/workspace/probe/effectcraft/sheets/command_Layer_Mask.png`
- command Layer > New (1개): `data/workspace/probe/effectcraft/sheets/command_Layer_New.png`
- command Layer > Switches (1개): `data/workspace/probe/effectcraft/sheets/command_Layer_Switches.png`
- command Layer > Transform (1개): `data/workspace/probe/effectcraft/sheets/command_Layer_Transform.png`
- command shape (1개): `data/workspace/probe/effectcraft/sheets/command_shape.png`
- effect Blur & Sharpen (6개): `data/workspace/probe/effectcraft/sheets/effect_Blur_Sharpen.png`
- effect Channel (2개): `data/workspace/probe/effectcraft/sheets/effect_Channel.png`
- effect Color Correction (15개): `data/workspace/probe/effectcraft/sheets/effect_Color_Correction.png`
- effect Distort (12개): `data/workspace/probe/effectcraft/sheets/effect_Distort.png`
- effect Generate (18개): `data/workspace/probe/effectcraft/sheets/effect_Generate.png`
- effect Immersive Video (8개): `data/workspace/probe/effectcraft/sheets/effect_Immersive_Video.png`
- effect Keying (7개): `data/workspace/probe/effectcraft/sheets/effect_Keying.png`
- effect Matte (1개): `data/workspace/probe/effectcraft/sheets/effect_Matte.png`
- effect Noise & Grain (4개): `data/workspace/probe/effectcraft/sheets/effect_Noise_Grain.png`
- effect Obsolete (1개): `data/workspace/probe/effectcraft/sheets/effect_Obsolete.png`
- effect Perspective (6개): `data/workspace/probe/effectcraft/sheets/effect_Perspective.png`
- effect Simulation (15개): `data/workspace/probe/effectcraft/sheets/effect_Simulation.png`
- effect Stylize (18개): `data/workspace/probe/effectcraft/sheets/effect_Stylize.png`
- effect Time (2개): `data/workspace/probe/effectcraft/sheets/effect_Time.png`
- effect Utility (3개): `data/workspace/probe/effectcraft/sheets/effect_Utility.png`
- preset Backgrounds (23개): `data/workspace/probe/effectcraft/sheets/preset_Backgrounds.png`
- preset Behaviors (22개): `data/workspace/probe/effectcraft/sheets/preset_Behaviors.png`
- preset Transitions (23개): `data/workspace/probe/effectcraft/sheets/preset_Transitions.png`
- preset blurIn (1개): `data/workspace/probe/effectcraft/sheets/preset_blurIn.png`
- preset bounceInWords (1개): `data/workspace/probe/effectcraft/sheets/preset_bounceInWords.png`
- preset dropInLines (1개): `data/workspace/probe/effectcraft/sheets/preset_dropInLines.png`
- preset fadeUpCharacters (1개): `data/workspace/probe/effectcraft/sheets/preset_fadeUpCharacters.png`
- preset jitter (1개): `data/workspace/probe/effectcraft/sheets/preset_jitter.png`
- preset scramble (1개): `data/workspace/probe/effectcraft/sheets/preset_scramble.png`
- preset trackingIn (1개): `data/workspace/probe/effectcraft/sheets/preset_trackingIn.png`
- preset typewriter (1개): `data/workspace/probe/effectcraft/sheets/preset_typewriter.png`

## 안 될 때 이유(상태별 command.list — 많은 순)
- select a layer first — 156
- select keyframes first — 125
- the render queue is empty — 50
- no current track: use Track Motion first — 50
- the selected layers have no masks — 40
- select an item in the Project panel first — 35
- select footage in the Project panel — 32
- open footage in the Footage panel first — 30
- edit text or select a text layer — 28
- select a text layer first — 24
- add properties to Essential Graphics first — 20
- the composition has no guides — 15
- select a camera layer — 15
- select a precomp layer with Essential Properties — 15
- nothing to undo — 10
