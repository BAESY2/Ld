"""벤더 프로파일 (Phase L1) — 벤더중립 역할 → 벤더별 디바이스/주소/명령어.

학습(docs/research/ladder-knowledge-base.md §2)에서 확인된 핵심:
**주소 모델이 벤더마다 근본적으로 호환 불가**하다.
  - LS XGK  : 디바이스 문자 + (현재 구현은 10진) — 입출력 공용 P
  - 미쓰비시 : X/Y 입출력 분리, **8진(octal)** I/O 번호
  - 지멘스   : I/Q/M + **byte.bit** (%I0.0)
  - 옴론     : CIO + **channel.bit**(16비트/워드), 타이머 **감산(countdown)**

그래서 파이프라인은 벤더중립 ``DeviceRole`` 로 사고하고, 마지막에 프로파일이
역할 → 실제 디바이스 문자·주소 표기·명령어 니모닉으로 렌더한다.

주의: ``LS_XGK`` 는 **기존 동작을 그대로 보존**한다(P0000/M0000/D00000 …, 10진).
실제 XGK 의 16진 비트주소화는 후속 정밀화 과제로 둔다(기존 골든/테스트 보호).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from app.models import DeviceClass, IODirection


class DeviceRole(StrEnum):
    """벤더중립 디바이스 역할."""

    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INTERNAL = "INTERNAL"
    KEEP = "KEEP"
    LINK = "LINK"
    TIMER = "TIMER"
    COUNTER = "COUNTER"
    DATA = "DATA"
    STEP = "STEP"


# DeviceClass(LS 체계) + 방향 → 벤더중립 역할
_NON_IO_ROLE: dict[DeviceClass, DeviceRole] = {
    DeviceClass.M: DeviceRole.INTERNAL,
    DeviceClass.K: DeviceRole.KEEP,
    DeviceClass.L: DeviceRole.LINK,
    DeviceClass.T: DeviceRole.TIMER,
    DeviceClass.C: DeviceRole.COUNTER,
    DeviceClass.D: DeviceRole.DATA,
}


def role_of(device_class: DeviceClass, direction: IODirection | None = None) -> DeviceRole:
    """DeviceClass(+방향)를 벤더중립 역할로 변환한다.

    P 는 방향에 따라 INPUT/OUTPUT 으로 갈린다(미쓰비시 X/Y 분리를 위해).
    방향 미지정 시 INPUT 으로 본다(기존 allocate(.., P) 호출 호환).
    """
    if device_class == DeviceClass.P:
        return DeviceRole.OUTPUT if direction == IODirection.OUTPUT else DeviceRole.INPUT
    return _NON_IO_ROLE[device_class]


@dataclass(frozen=True)
class VendorProfile:
    """벤더별 디바이스/주소/명령어 규칙."""

    name: str
    role_letter: Mapping[DeviceRole, str]
    letter_width: Mapping[str, int] = field(default_factory=dict)
    octal_letters: frozenset[str] = frozenset()
    bits_per_word: int = 0  # 0=문자+인덱스, >0=비트주소(byte.bit / channel.bit)
    bit_template: str = "%{letter}{word}.{bit}"
    timer_is_countdown: bool = False
    il_style: str = "orb"  # "orb"=LD/AND/ORB 계열, "stl"=지멘스 A/O 블록
    mnemonics: Mapping[str, str] = field(default_factory=dict)

    def letter_of(self, role: DeviceRole) -> str:
        """역할 → 디바이스 문자."""
        return self.role_letter[role]

    def index_key(
        self, device_class: DeviceClass, direction: IODirection | None = None
    ) -> str:
        """인덱스 공간 키 = 디바이스 문자.

        LS 는 INPUT/OUTPUT 둘 다 'P' 라 인덱스를 공유하고,
        미쓰비시는 X/Y 로 갈려 별도 인덱스를 쓴다.
        """
        return self.letter_of(role_of(device_class, direction))

    def format_address(
        self,
        device_class: DeviceClass,
        index: int,
        direction: IODirection | None = None,
    ) -> str:
        """역할/인덱스를 벤더별 주소 문자열로 표기한다."""
        role = role_of(device_class, direction)
        letter = self.letter_of(role)

        if self.bits_per_word:
            word, bit = divmod(index, self.bits_per_word)
            return self.bit_template.format(letter=letter, word=word, bit=bit)

        body = format(index, "o") if letter in self.octal_letters else str(index)
        width = self.letter_width.get(letter, 0)
        if width:
            body = body.rjust(width, "0")
        return f"{letter}{body}"

    def mnemonic(self, op: str) -> str:
        """명령어 니모닉(없으면 op 그대로)."""
        return self.mnemonics.get(op, op)


# ---------------------------------------------------------------------------
# 프로파일 인스턴스
# ---------------------------------------------------------------------------

# LS XGK — 기본값. 기존 동작 보존(10진, 입출력 공용 P, D=5자리).
LS_XGK = VendorProfile(
    name="LS_XGK",
    role_letter={
        DeviceRole.INPUT: "P",
        DeviceRole.OUTPUT: "P",
        DeviceRole.INTERNAL: "M",
        DeviceRole.KEEP: "K",
        DeviceRole.LINK: "L",
        DeviceRole.TIMER: "T",
        DeviceRole.COUNTER: "C",
        DeviceRole.DATA: "D",
        DeviceRole.STEP: "S",
    },
    letter_width={"P": 4, "M": 4, "K": 4, "L": 4, "T": 4, "C": 4, "D": 5, "S": 4},
    mnemonics={
        "contact_no": "LOAD",
        "contact_nc": "LOAD NOT",
        "and_no": "AND",
        "and_nc": "AND NOT",
        "or_block": "ORB",
        "coil": "OUT",
        "set": "SET",
        "reset": "RST",
        "oneshot_rising": "OUTP",
        "oneshot_falling": "OUTN",
        "timer_on": "TON",
        "counter_up": "CTU",
    },
)

# 미쓰비시 MELSEC FX — X/Y 입출력 분리, 8진 I/O.
MITSUBISHI_FX = VendorProfile(
    name="MITSUBISHI_FX",
    role_letter={
        DeviceRole.INPUT: "X",
        DeviceRole.OUTPUT: "Y",
        DeviceRole.INTERNAL: "M",
        DeviceRole.KEEP: "M",
        DeviceRole.LINK: "B",
        DeviceRole.TIMER: "T",
        DeviceRole.COUNTER: "C",
        DeviceRole.DATA: "D",
        DeviceRole.STEP: "S",
    },
    letter_width={},  # 패딩 없음(X0, X10, M0 …)
    octal_letters=frozenset({"X", "Y"}),
    mnemonics={
        "contact_no": "LD",
        "contact_nc": "LDI",
        "and_no": "AND",
        "and_nc": "ANI",
        "or_block": "ORB",
        "coil": "OUT",
        "set": "SET",
        "reset": "RST",
        "oneshot_rising": "PLS",
        "oneshot_falling": "PLF",
        "timer_on": "OUT T",
        "counter_up": "OUT C",
    },
)

# 지멘스 S7-1200/1500 — byte.bit (%I0.0), 8비트/바이트.
SIEMENS_S7 = VendorProfile(
    name="SIEMENS_S7",
    role_letter={
        DeviceRole.INPUT: "I",
        DeviceRole.OUTPUT: "Q",
        DeviceRole.INTERNAL: "M",
        DeviceRole.KEEP: "M",
        DeviceRole.LINK: "M",
        DeviceRole.TIMER: "T",
        DeviceRole.COUNTER: "C",
        DeviceRole.DATA: "DB",
        DeviceRole.STEP: "M",
    },
    bits_per_word=8,
    bit_template="%{letter}{word}.{bit}",
    il_style="stl",
    mnemonics={
        "contact_no": "A",
        "contact_nc": "AN",
        "and_no": "A",
        "and_nc": "AN",
        "or_no": "O",
        "coil": "=",
        "set": "S",
        "reset": "R",
        "oneshot_rising": "P",
        "oneshot_falling": "N",
        "timer_on": "TON",
        "counter_up": "CTU",
    },
)

# 옴론 CJ/CP — channel.bit (16비트/워드), 타이머 감산.
OMRON_CJ = VendorProfile(
    name="OMRON_CJ",
    role_letter={
        DeviceRole.INPUT: "CIO",
        DeviceRole.OUTPUT: "CIO",
        DeviceRole.INTERNAL: "W",
        DeviceRole.KEEP: "H",
        DeviceRole.LINK: "CIO",
        DeviceRole.TIMER: "T",
        DeviceRole.COUNTER: "C",
        DeviceRole.DATA: "D",
        DeviceRole.STEP: "W",
    },
    bits_per_word=16,
    bit_template="{letter}{word}.{bit:02d}",
    timer_is_countdown=True,
    mnemonics={
        "contact_no": "LD",
        "contact_nc": "LD NOT",
        "and_no": "AND",
        "and_nc": "AND NOT",
        "or_block": "ORB",
        "coil": "OUT",
        "set": "SET",
        "reset": "RSET",
        "oneshot_rising": "DIFU",
        "oneshot_falling": "DIFD",
        "timer_on": "TIM",
        "counter_up": "CNT",
    },
)


_PROFILES: dict[str, VendorProfile] = {
    p.name: p for p in (LS_XGK, MITSUBISHI_FX, SIEMENS_S7, OMRON_CJ)
}

DEFAULT_PROFILE = LS_XGK


def get_profile(name: str) -> VendorProfile:
    """이름으로 프로파일을 찾는다(없으면 KeyError)."""
    return _PROFILES[name]


def available_profiles() -> list[str]:
    """등록된 프로파일 이름 목록."""
    return list(_PROFILES)
