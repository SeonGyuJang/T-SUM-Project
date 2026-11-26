"""윈도우 명령 프롬프트(cp949)나 파이프·파일로 출력을 보낼 때 ✓·⚠·⏳ 같은 기호 때문에
UnicodeEncodeError로 멈추지 않게 한다. 표시할 수 없는 기호만 '?'로 바뀌고 한글은 그대로 나온다.
각 스크립트 맨 위에서 import만 하면 된다."""
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # 이미 다른 것으로 바뀐 출력(노트북 등)
        pass
