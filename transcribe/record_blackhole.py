"""
BlackHole Discord 錄音 + 轉錄工具

前置設定（只需做一次）：
  1. brew install blackhole-2ch
  2. 開啟「音訊 MIDI 設定」(Audio MIDI Setup)
     - 左下角 + → 建立「多重輸出裝置」(Multi-Output Device)
     - 勾選：你的耳機 + BlackHole 2ch
     - 將耳機設為「主裝置」(drift correction 只勾 BlackHole)
  3. 系統設定 → 聲音 → 輸出 → 選「多重輸出裝置」
     （或只在 Discord 設定 → 語音 → 輸出裝置 → 選「多重輸出裝置」）

使用方式：
  python record_blackhole.py              # 錄音，Ctrl+C 停止
  python record_blackhole.py --transcribe # 錄音完自動轉錄
  python record_blackhole.py --list       # 列出所有音訊裝置
"""

import sys
import time
import queue
import argparse
import datetime
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path

OUTPUT_DIR = Path("recordings")
OUTPUT_DIR.mkdir(exist_ok=True)

SAMPLE_RATE = 48000
CHANNELS = 2
BLOCKSIZE = 1024


def list_devices():
    """列出所有音訊輸入裝置。"""
    print("\n可用音訊裝置：")
    print("-" * 60)
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            marker = " ◀ BlackHole" if "blackhole" in dev["name"].lower() else ""
            print(f"  [{i:2d}] {dev['name']}{marker}")
    print()


def find_blackhole_device() -> int | None:
    """自動尋找 BlackHole 輸入裝置的 index。"""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if "blackhole" in dev["name"].lower() and dev["max_input_channels"] > 0:
            return i
    return None


def record(device_index: int, output_path: Path) -> Path:
    """從指定裝置錄音，Ctrl+C 停止，儲存為 WAV。"""
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()
    stop_event = threading.Event()

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  [警告] {status}")
        audio_queue.put(indata.copy())

    print(f"\n錄音中... 按 Ctrl+C 停止")
    print(f"輸出裝置：{sd.query_devices(device_index)['name']}")
    print(f"儲存至：{output_path}\n")

    chunks = []
    start_time = time.time()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            device=device_index,
            blocksize=BLOCKSIZE,
            callback=callback,
        ):
            while True:
                try:
                    chunk = audio_queue.get(timeout=0.5)
                    chunks.append(chunk)
                    elapsed = int(time.time() - start_time)
                    print(f"\r  錄音時間：{elapsed // 60:02d}:{elapsed % 60:02d}", end="", flush=True)
                except queue.Empty:
                    continue
    except KeyboardInterrupt:
        print("\n\n停止錄音...")

    if chunks:
        audio_data = np.concatenate(chunks, axis=0)
        sf.write(output_path, audio_data, SAMPLE_RATE)
        duration = len(audio_data) / SAMPLE_RATE
        print(f"已儲存：{output_path}  ({duration:.1f} 秒)")
    else:
        print("沒有錄到任何音訊。")
        return None

    return output_path


def transcribe(audio_path: Path, model_name: str = "base") -> str:
    """使用 Whisper 轉錄音訊。"""
    try:
        import whisper
    except ImportError:
        print("請先安裝 openai-whisper：pip install openai-whisper")
        return ""

    print(f"\n載入 Whisper 模型（{model_name}）...")
    model = whisper.load_model(model_name)

    print("轉錄中...")
    result = model.transcribe(str(audio_path), language="zh", verbose=False)
    text = result["text"].strip()

    # 儲存逐字稿
    transcript_path = audio_path.with_suffix(".txt")
    transcript_path.write_text(text, encoding="utf-8")
    print(f"\n逐字稿：\n{'─' * 40}\n{text}\n{'─' * 40}")
    print(f"\n已儲存逐字稿：{transcript_path}")

    return text


def main():
    parser = argparse.ArgumentParser(description="BlackHole Discord 錄音工具")
    parser.add_argument("--list", action="store_true", help="列出所有音訊裝置")
    parser.add_argument("--device", type=int, default=None, help="指定裝置 index（預設自動偵測 BlackHole）")
    parser.add_argument("--transcribe", action="store_true", help="錄音完自動用 Whisper 轉錄")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper 模型大小（預設 base）")
    args = parser.parse_args()

    if args.list:
        list_devices()
        return

    # 尋找 BlackHole 裝置
    device_index = args.device
    if device_index is None:
        device_index = find_blackhole_device()
        if device_index is None:
            print("找不到 BlackHole 裝置！")
            print("請執行 brew install blackhole-2ch 安裝，")
            print("或用 --list 查看可用裝置，再用 --device <index> 指定。")
            sys.exit(1)

    # 產生輸出檔名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"discord_{timestamp}.wav"

    # 錄音
    saved_path = record(device_index, output_path)

    # 轉錄
    if saved_path and args.transcribe:
        transcribe(saved_path, args.model)


if __name__ == "__main__":
    main()
