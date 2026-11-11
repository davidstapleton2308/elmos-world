from elmos_controller_lab.api_probe import run_probe


def test_api_probe_is_read_only_and_reports_supported_layers():
    result = run_probe()
    assert "apis" in result
    assert "xinput" in result["apis"]
    assert "sdl_gamecontroller" in result["apis"]
    assert "hidapi" in result["apis"]
    assert result["apis"]["windows_gaming_input"]["status"] == "not implemented in this probe"
