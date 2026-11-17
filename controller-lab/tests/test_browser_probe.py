import json
from urllib.request import Request, urlopen

from elmos_controller_lab.browser_probe import BrowserProbeServer


def test_local_browser_probe_serves_page_and_accepts_gamepad_snapshot():
    server = BrowserProbeServer()
    url = server.start(open_browser=False)
    try:
        with urlopen(url, timeout=3) as response:
            page = response.read().decode("utf-8")
            assert response.status == 200
            assert "navigator.getGamepads" in page
            assert "fetch('/report'" in page

        payload = json.dumps({
            "time": 123456,
            "devices": [{"index": 0, "id": "Virtual Xbox Controller", "mapping": "standard"}],
        }).encode("utf-8")
        request = Request(url + "report", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=3) as response:
            assert response.status == 204
        snapshot = server.snapshot()
        assert snapshot["time"] == 123456
        assert snapshot["devices"][0]["id"] == "Virtual Xbox Controller"
    finally:
        server.stop()
