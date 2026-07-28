#!/usr/bin/env python3
"""从 SCAIL2 3clip 模板生成指定片段数量的 API 工作流。"""

import argparse
import json
from pathlib import Path

from opc_cli.scail import build_scail_workflow, unresolved_references


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = ROOT / "workflows" / "SCAIL2-3clips.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", type=int, help="连续推理片段数量，至少为 1")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    template_path = arguments.template.resolve()
    output_path = arguments.output or ROOT / "workflows" / f"SCAIL2-{arguments.clips}clips.json"
    if not template_path.is_file():
        parser.error(f"模板不存在: {template_path}")
    try:
        template = json.loads(template_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        parser.error(f"模板不是有效 JSON: {error}")

    workflow = build_scail_workflow(template, arguments.clips)
    unresolved = unresolved_references(workflow)
    if unresolved:
        parser.error("生成结果存在悬空节点引用: " + ", ".join(sorted(unresolved)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)


if __name__ == "__main__":
    main()
