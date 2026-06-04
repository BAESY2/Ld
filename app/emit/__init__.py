"""벤더 래더 에미터 패키지 (Phase N)."""

from __future__ import annotations

from app.emit.ladder_il import emit
from app.memory_map import DeviceAllocator
from app.models import StateMachineSpec
from app.transpiler import transpile_st
from app.vendors.profiles import DEFAULT_PROFILE, VendorProfile

__all__ = ["emit", "render_for_vendor"]


def render_for_vendor(
    st_code: str,
    spec: StateMachineSpec,
    profile: VendorProfile = DEFAULT_PROFILE,
) -> str:
    """명세+ST 를 대상 벤더의 주소·명령어로 렌더한다.

    프로파일로 디바이스를 선발급(미쓰비시면 X/Y 8진 등) → 트랜스파일로 주소 주입
    → 벤더 명령어 텍스트로 에미트.
    """
    allocator = DeviceAllocator(profile).build_from_spec(spec)
    program = transpile_st(st_code, allocator)
    return emit(program, profile)
