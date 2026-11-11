from elmos_controller_lab.api_probe import run_probe


def test_api_probe_is_read_only_and_reports_supported_layers():
    result = run_probe()
    assert "apis" in result
    assert "xinput" in result["apis"]
    assert "sdl_gamecontroller" in result["apis"]
    assert "hidapi" in result["apis"]
    assert result["apis"]["windows_gaming_input"]["status"] == "not queried"


def test_api_probe_uses_bridge_for_windows_gaming_input():
    class FakeBridge:
        def request(self, operation, timeout=20):
            assert operation == "wgi"
            return {"available": True, "devices": [{"name": "Virtual Gamepad", "vendorId": 0x054C, "productId": 0x05C4}]}

    result = run_probe(bridge=FakeBridge())
    assert result["apis"]["windows_gaming_input"]["available"] is True
    assert result["apis"]["windows_gaming_input"]["devices"][0]["name"] == "Virtual Gamepad"
