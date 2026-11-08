# photocraft 기능 시험 결과(engine/craft/probe.py)

| 종류 | 결과 | 수 |
|---|---|---|
| command | error | 55 |
| command | needs_context | 222 |
| command | needs_params | 209 |
| command | ok | 464 |
| command | untested | 4 |

## 견본 판(기본값 그대로 · 이미지 · 픽셀 레이어에 적용해 화면이 바뀐 것) — Read 로 본다
- command Edit (4개): `data/workspace/probe/photocraft/sheets/command_Edit.png`
- command Edit > Transform (5개): `data/workspace/probe/photocraft/sheets/command_Edit_Transform.png`
- command File (1개): `data/workspace/probe/photocraft/sheets/command_File.png`
- command File > Automate (1개): `data/workspace/probe/photocraft/sheets/command_File_Automate.png`
- command Filter > Blur (9개): `data/workspace/probe/photocraft/sheets/command_Filter_Blur.png`
- command Filter > Blur Gallery (5개): `data/workspace/probe/photocraft/sheets/command_Filter_Blur_Gallery.png`
- command Filter > Distort (6개): `data/workspace/probe/photocraft/sheets/command_Filter_Distort.png`
- command Filter > Noise (1개): `data/workspace/probe/photocraft/sheets/command_Filter_Noise.png`
- command Filter > Other (5개): `data/workspace/probe/photocraft/sheets/command_Filter_Other.png`
- command Filter > Pixelate (6개): `data/workspace/probe/photocraft/sheets/command_Filter_Pixelate.png`
- command Filter > Render (9개): `data/workspace/probe/photocraft/sheets/command_Filter_Render.png`
- command Filter > Sharpen (4개): `data/workspace/probe/photocraft/sheets/command_Filter_Sharpen.png`
- command Filter > Stylize (8개): `data/workspace/probe/photocraft/sheets/command_Filter_Stylize.png`
- command Image (4개): `data/workspace/probe/photocraft/sheets/command_Image.png`
- command Image > Adjustments (10개): `data/workspace/probe/photocraft/sheets/command_Image_Adjustments.png`
- command Image > Image Rotation (5개): `data/workspace/probe/photocraft/sheets/command_Image_Image_Rotation.png`
- command Image > Mode (5개): `data/workspace/probe/photocraft/sheets/command_Image_Mode.png`
- command Layer (2개): `data/workspace/probe/photocraft/sheets/command_Layer.png`
- command Layer > Arrange (1개): `data/workspace/probe/photocraft/sheets/command_Layer_Arrange.png`
- command Layer > Delete (1개): `data/workspace/probe/photocraft/sheets/command_Layer_Delete.png`
- command Layer > Layer Mask (1개): `data/workspace/probe/photocraft/sheets/command_Layer_Layer_Mask.png`
- command Layer > Layer Style (7개): `data/workspace/probe/photocraft/sheets/command_Layer_Layer_Style.png`
- command Layer > New (2개): `data/workspace/probe/photocraft/sheets/command_Layer_New.png`
- command Layer > New Adjustment Layer (6개): `data/workspace/probe/photocraft/sheets/command_Layer_New_Adjustment_Layer.png`
- command Layer > New Fill Layer (3개): `data/workspace/probe/photocraft/sheets/command_Layer_New_Fill_Layer.png`
- command Type (1개): `data/workspace/probe/photocraft/sheets/command_Type.png`
- command 기타 (56개): `data/workspace/probe/photocraft/sheets/command_.png`

## 안 될 때 이유(상태별 command.list — 많은 순)
- no active layer — 331
- filters need a pixel layer (active layer is a Type layer) — 119
- filters need a pixel layer (active layer is a Shape layer) — 119
- select a type layer — 81
- no selection — 63
- active layer is a Type layer, not a pixel layer — 52
- active layer is a Shape layer, not a pixel layer — 52
- the active layer is not a smart object — 48
- the document has no layer comps — 44
- select a video layer — 44
- the active layer is not a type layer — 42
- select three or more layers to distribute — 32
- the clipboard is empty — 24
- no timeline (create one first) — 20
- the active layer is a Pixel layer, not a smart object — 19
