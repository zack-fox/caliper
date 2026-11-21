"""界面装配层：设备增改删与证据包预览。"""

from __future__ import annotations

import pytest

from app.controller import AppController, ControllerError
from core.model.entities import Asset


def _asset(name: str = "设备A", ip: str = "192.0.2.10", package: str | None = None) -> Asset:
    return Asset(
        device_name=name,
        ip=ip,
        importance="一般",
        guide="三级-安全通用要求",
        asset_type="服务器",
        evidence_package=package,
    )


def test_add_update_and_remove_asset() -> None:
    controller = AppController()
    controller.add_asset(_asset())
    with pytest.raises(ControllerError):
        controller.add_asset(_asset())

    controller.update_asset("设备A", _asset("设备B"))
    assert [asset.device_name for asset in controller.project.assets] == ["设备B"]

    controller.add_asset(_asset("设备C", ip="192.0.2.11"))
    with pytest.raises(ControllerError):
        controller.update_asset("设备B", _asset("设备C", ip="192.0.2.12"))
    with pytest.raises(ControllerError):
        controller.update_asset("不存在的设备", _asset())

    controller.remove_asset("设备B")
    assert [asset.device_name for asset in controller.project.assets] == ["设备C"]


def test_inspect_evidence_states() -> None:
    controller = AppController()
    empty = controller.inspect_evidence(None)
    assert empty.ok is False
    assert "未关联" in empty.message

    missing = controller.inspect_evidence("不存在的包")
    assert missing.ok is False
    assert "不存在" in missing.message
