"""
ONNX 모델 변환 스크립트 (오프라인, 최초 1회 실행)

pytorch_model.bin → model.onnx 변환
변환 완료 후에는 torch/transformers 없이 onnxruntime만으로 동작합니다.

사용법:
    cd backend
    pip install torch transformers
    python convert_model.py

    # 또는 특정 경로 지정
    python convert_model.py ./models/onnx/jhgan_ko-sroberta-multitask

참고:
    Windows에서도 별도 환경변수 없이 실행 가능 (cp949 인코딩 자동 처리)
"""

import sys
import os
from pathlib import Path

# Windows cp949 인코딩 오류 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def convert_to_onnx(model_dir: str) -> None:
    model_path = Path(model_dir)

    if not model_path.exists():
        print(f"[ERROR] 모델 디렉토리를 찾을 수 없습니다: {model_path}")
        sys.exit(1)

    onnx_file = model_path / "model.onnx"
    if onnx_file.exists():
        print(f"[SKIP] model.onnx가 이미 존재합니다: {onnx_file}")
        print(f"       삭제 후 다시 실행하세요: del {onnx_file}")
        return

    pytorch_file = model_path / "pytorch_model.bin"
    safetensors_file = model_path / "model.safetensors"

    if not pytorch_file.exists() and not safetensors_file.exists():
        print(f"[ERROR] 변환할 모델 파일이 없습니다:")
        print(f"        pytorch_model.bin 또는 model.safetensors가 필요합니다")
        sys.exit(1)

    # 인터넷 접속 차단
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"

    print(f"[INFO] 모델 로드 중: {model_path}")

    import torch
    from transformers import AutoModel, AutoTokenizer, AutoConfig

    config = AutoConfig.from_pretrained(str(model_path))
    model = AutoModel.from_pretrained(str(model_path), config=config)
    tokenizer = AutoTokenizer.from_pretrained(str(model_path))

    model.eval()

    print(f"[INFO] 모델 로드 완료 (hidden_size: {config.hidden_size})")

    # 더미 입력 생성
    dummy = tokenizer("변환 테스트", return_tensors="pt")
    input_ids = dummy["input_ids"]
    attention_mask = dummy["attention_mask"]

    input_names = ["input_ids", "attention_mask"]
    output_names = ["last_hidden_state"]
    dynamic_axes = {
        "input_ids": {0: "batch_size", 1: "sequence_length"},
        "attention_mask": {0: "batch_size", 1: "sequence_length"},
        "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
    }

    inputs = (input_ids, attention_mask)

    # token_type_ids 지원 여부 확인
    if hasattr(config, "type_vocab_size") and config.type_vocab_size > 1:
        token_type_ids = torch.zeros_like(input_ids)
        inputs = (input_ids, attention_mask, token_type_ids)
        input_names.append("token_type_ids")
        dynamic_axes["token_type_ids"] = {0: "batch_size", 1: "sequence_length"}

    print(f"[INFO] ONNX 변환 시작...")

    export_kwargs = dict(
        input_names=input_names,
        output_names=output_names,
        dynamic_axes=dynamic_axes,
        opset_version=14,
        do_constant_folding=True,
    )

    # torch 2.4+ dynamo export는 onnxscript 필요 → legacy export 강제
    import inspect
    if "dynamo" in inspect.signature(torch.onnx.export).parameters:
        export_kwargs["dynamo"] = False

    torch.onnx.export(
        model,
        inputs,
        str(onnx_file),
        **export_kwargs,
    )

    size_mb = onnx_file.stat().st_size / (1024 * 1024)
    print(f"[OK] 변환 완료: {onnx_file} ({size_mb:.1f}MB)")
    print(f"[INFO] 이제 torch/transformers 없이 onnxruntime만으로 동작합니다.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        model_dir = sys.argv[1]
    else:
        model_dir = "./models/onnx/jhgan_ko-sroberta-multitask"

    convert_to_onnx(model_dir)
