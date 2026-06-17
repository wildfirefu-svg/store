# BaziQA Source Notes

Source repository: https://github.com/ChenJiangxi/BaziQA

Paper: https://arxiv.org/abs/2602.12889

Dataset files used by XuanJiZi:

- `contest8_2021.json`
- `contest8_2022.json`
- `contest8_2023.json`
- `contest8_2024.json`
- `contest8_2025.json`
- `celebrity50_zh.json`

License:

The upstream repository states that the dataset uses the MIT License. Keep the upstream license and attribution when vendoring or redistributing derived files.

XuanJiZi normalization:

- Contest8 questions are converted into JSONL rows with one question per line.
- `person_id`, `profile`, `birth`, `gender`, `question`, `options`, and `answer` are preserved.
- `source_year`, `contest_id`, and `domain` are added when available.
- Celebrity events are preserved as `verified_events` for timeline and life-event evaluation.

Recommended split:

- Development: Contest8 2021-2023
- Validation: Contest8 2024
- Locked test: Contest8 2025
- Timeline calibration: Celebrity50
