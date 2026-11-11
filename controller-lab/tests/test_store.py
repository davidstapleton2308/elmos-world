from elmos_controller_lab.mapping import ActionLayer, MappingProfile, StickTuning
from elmos_controller_lab.store import MappingStore


def test_mapping_profiles_are_saved_per_controller_game_and_target(tmp_path):
    store = MappingStore(tmp_path / "mappings.json")
    profile = MappingProfile(
        name="PS4 to Xbox test",
        button_map={"south": "east"},
        left_stick=StickTuning(deadzone=0.18, exponent=1.4, invert_y=True),
        layer=ActionLayer(activator="left_paddle", mode="hold", button_map={"south": "north"}),
    )
    store.save("ps4-guid", "game-123", "xbox-360-wired", profile)
    loaded = store.get("ps4-guid", "game-123", "xbox-360-wired")
    assert loaded.name == "PS4 to Xbox test"
    assert loaded.button_map == {"south": "east"}
    assert loaded.left_stick.deadzone == 0.18
    assert loaded.left_stick.invert_y is True
    assert loaded.layer is not None
    assert loaded.layer.button_map == {"south": "north"}


def test_mapping_profiles_are_isolated_between_devices_and_games(tmp_path):
    store = MappingStore(tmp_path / "mappings.json")
    store.save("device-a", "game-a", "dualsense", MappingProfile(name="A"))
    store.save("device-b", "game-a", "dualsense", MappingProfile(name="B"))
    store.save("device-a", "game-b", "dualsense", MappingProfile(name="C"))
    assert store.get("device-a", "game-a", "dualsense").name == "A"
    assert store.get("device-b", "game-a", "dualsense").name == "B"
    assert store.get("device-a", "game-b", "dualsense").name == "C"


def test_delete_profile_is_idempotent(tmp_path):
    store = MappingStore(tmp_path / "mappings.json")
    store.save("device", "game", "xbox-series-xs-bt", MappingProfile(name="test"))
    assert store.delete("device", "game", "xbox-series-xs-bt") is True
    assert store.delete("device", "game", "xbox-series-xs-bt") is False
    assert store.get("device", "game", "xbox-series-xs-bt").name == "Default"
