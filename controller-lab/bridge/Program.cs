using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Security.Principal;
using System.Text.Json;
using HIDMaestro;
using Windows.Gaming.Input;

internal static class Program
{
    private static readonly object OutputLock = new();
    private const string BackendSdkVersion = "2.1.0";
    private static HMContext? Context;
    private static readonly string DriverStampPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ElmosControllerLab", "hidmaestro-driver-version.txt");
    private static bool DriverPrepared => Context!.IsDriverInstalled &&
        File.Exists(DriverStampPath) &&
        string.Equals(File.ReadAllText(DriverStampPath).Trim(), BackendSdkVersion, StringComparison.Ordinal);
    private static readonly Dictionary<string, HMController> Controllers = new(StringComparer.OrdinalIgnoreCase);
    private static bool IsElevated()
    {
        try
        {
            using var identity = WindowsIdentity.GetCurrent();
            return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
        }
        catch { return false; }
    }

    private static void Emit(object value)
    {
        lock (OutputLock)
        {
            Console.Out.WriteLine(JsonSerializer.Serialize(value));
            Console.Out.Flush();
        }
    }

    private static string? Text(JsonElement node, string name, string? fallback = null)
    {
        if (node.ValueKind == JsonValueKind.Object &&
            node.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String)
            return value.GetString();
        return fallback;
    }

    private static double Number(JsonElement node, string name, double fallback = 0)
    {
        if (node.ValueKind == JsonValueKind.Object &&
            node.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number &&
            value.TryGetDouble(out var number) && double.IsFinite(number))
            return number;
        return fallback;
    }

    private static bool Bool(JsonElement node, string name, bool fallback = false)
    {
        if (node.ValueKind == JsonValueKind.Object &&
            node.TryGetProperty(name, out var value) &&
            (value.ValueKind == JsonValueKind.True || value.ValueKind == JsonValueKind.False))
            return value.GetBoolean();
        return fallback;
    }

    private static double Clamp(double value, double min, double max) =>
        double.IsFinite(value) ? Math.Max(min, Math.Min(max, value)) : 0;

    private static float SignedAxis(JsonElement axes, string name) =>
        (float)((Clamp(Number(axes, name), -1, 1) + 1.0) * 0.5);

    private static float TriggerAxis(JsonElement axes, string name) =>
        (float)Clamp(Number(axes, name), 0, 1);

    private static HMButton Button(string name) => name.ToLowerInvariant() switch
    {
        "south" => HMButton.A,
        "east" => HMButton.B,
        "west" => HMButton.X,
        "north" => HMButton.Y,
        "left_shoulder" => HMButton.LeftBumper,
        "right_shoulder" => HMButton.RightBumper,
        "back" => HMButton.Back,
        "start" => HMButton.Start,
        "guide" => HMButton.Guide,
        "left_stick" => HMButton.LeftStick,
        "right_stick" => HMButton.RightStick,
        "touchpad_click" => HMButton.Touchpad,
        "share" => HMButton.Share,
        "left_paddle" => HMButton.LeftPaddle,
        "right_paddle" => HMButton.RightPaddle,
        "left_paddle2" => HMButton.LeftPaddle2,
        "right_paddle2" => HMButton.RightPaddle2,
        "misc1" => HMButton.Misc1,
        _ => HMButton.None
    };

    private static HMHat ReadHat(JsonElement state)
    {
        var directions = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (state.TryGetProperty("dpad", out var dpad) && dpad.ValueKind == JsonValueKind.Array)
            foreach (var item in dpad.EnumerateArray())
                if (item.ValueKind == JsonValueKind.String && item.GetString() is string s)
                    directions.Add(s);
        bool u = directions.Contains("up"), r = directions.Contains("right");
        bool d = directions.Contains("down"), l = directions.Contains("left");
        if (u && r) return HMHat.NorthEast;
        if (d && r) return HMHat.SouthEast;
        if (d && l) return HMHat.SouthWest;
        if (u && l) return HMHat.NorthWest;
        if (u) return HMHat.North;
        if (r) return HMHat.East;
        if (d) return HMHat.South;
        if (l) return HMHat.West;
        return HMHat.None;
    }

    private static HMGamepadState BuildState(HMProfile profile, JsonElement root)
    {
        var axes = root.TryGetProperty("axes", out var axisNode) ? axisNode : default;
        var result = new HMGamepadState
        {
            Axes = HMGamepadStateHelpers.StandardAxes(
                profile,
                leftStickX: SignedAxis(axes, "left_x"),
                leftStickY: SignedAxis(axes, "left_y"),
                rightStickX: SignedAxis(axes, "right_x"),
                rightStickY: SignedAxis(axes, "right_y"),
                leftTrigger: TriggerAxis(axes, "left_trigger"),
                rightTrigger: TriggerAxis(axes, "right_trigger")),
            Hat = ReadHat(root)
        };

        if (root.TryGetProperty("buttons", out var buttons) && buttons.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in buttons.EnumerateArray())
                if (item.ValueKind == JsonValueKind.String && item.GetString() is string name)
                    result.Buttons |= Button(name);
        }

        // Advanced axes can address any HID usage declared by a wheel,
        // throttle, flight stick or custom profile. Values are normalized 0..1.
        if (axes.ValueKind == JsonValueKind.Object)
        {
            foreach (var pair in axes.EnumerateObject())
            {
                if (Enum.TryParse<HMAxis>(pair.Name, true, out var axis) &&
                    axis != HMAxis.None && pair.Value.ValueKind == JsonValueKind.Number &&
                    pair.Value.TryGetSingle(out var value))
                {
                    result.Axes ??= new Dictionary<HMAxis, float>();
                    result.Axes[axis] = (float)Clamp(value, 0, 1);
                }
            }
        }
        if (root.TryGetProperty("extra_axes", out var extra) && extra.ValueKind == JsonValueKind.Object)
        {
            foreach (var pair in extra.EnumerateObject())
            {
                if (Enum.TryParse<HMAxis>(pair.Name, true, out var axis) &&
                    axis != HMAxis.None && pair.Value.ValueKind == JsonValueKind.Number &&
                    pair.Value.TryGetSingle(out var value))
                {
                    result.Axes ??= new Dictionary<HMAxis, float>();
                    result.Axes[axis] = (float)Clamp(value, 0, 1);
                }
            }
        }

        if (root.TryGetProperty("motion", out var motion) && motion.ValueKind == JsonValueKind.Object)
        {
            result.GyroDpsX = (float)Clamp(Number(motion, "gyro_x"), -4000, 4000);
            result.GyroDpsY = (float)Clamp(Number(motion, "gyro_y"), -4000, 4000);
            result.GyroDpsZ = (float)Clamp(Number(motion, "gyro_z"), -4000, 4000);
            result.AccelGX = (float)Clamp(Number(motion, "accel_x"), -16, 16);
            result.AccelGY = (float)Clamp(Number(motion, "accel_y"), -16, 16);
            result.AccelGZ = (float)Clamp(Number(motion, "accel_z"), -16, 16);
            result.GyroPitch = (short)Clamp(Number(motion, "raw_gyro_pitch"), short.MinValue, short.MaxValue);
            result.GyroYaw = (short)Clamp(Number(motion, "raw_gyro_yaw"), short.MinValue, short.MaxValue);
            result.GyroRoll = (short)Clamp(Number(motion, "raw_gyro_roll"), short.MinValue, short.MaxValue);
            result.AccelX = (short)Clamp(Number(motion, "raw_accel_x"), short.MinValue, short.MaxValue);
            result.AccelY = (short)Clamp(Number(motion, "raw_accel_y"), short.MinValue, short.MaxValue);
            result.AccelZ = (short)Clamp(Number(motion, "raw_accel_z"), short.MinValue, short.MaxValue);
        }

        if (root.TryGetProperty("touchpads", out var touchpads) && touchpads.ValueKind == JsonValueKind.Array)
        {
            var contacts = touchpads.EnumerateArray().Take(2).ToArray();
            if (contacts.Length > 0)
            {
                var p = contacts[0];
                result.TouchpadFinger0Active = Bool(p, "active");
                result.TouchpadFinger0X = (ushort)Clamp(Number(p, "x"), 0, 1919);
                result.TouchpadFinger0Y = (ushort)Clamp(Number(p, "y"), 0, 1079);
                result.TouchpadFinger0Pressure = (float)Clamp(Number(p, "pressure"), 0, 1);
                result.TouchpadFinger0Id = (byte)Clamp(Number(p, "tracking_id"), 0, 127);
            }
            if (contacts.Length > 1)
            {
                var p = contacts[1];
                result.TouchpadFinger1Active = Bool(p, "active");
                result.TouchpadFinger1X = (ushort)Clamp(Number(p, "x"), 0, 1919);
                result.TouchpadFinger1Y = (ushort)Clamp(Number(p, "y"), 0, 1079);
                result.TouchpadFinger1Pressure = (float)Clamp(Number(p, "pressure"), 0, 1);
                result.TouchpadFinger1Id = (byte)Clamp(Number(p, "tracking_id"), 0, 127);
            }
        }
        result.TouchpadPacketCounter = (byte)Clamp(Number(root, "touchpad_packet_counter"), 0, 255);
        result.SensorTimestamp = (uint)Clamp(Number(root, "sensor_timestamp"), 0, uint.MaxValue);

        if (root.TryGetProperty("battery", out var battery) && battery.ValueKind == JsonValueKind.Number)
        {
            var percent = Clamp(battery.GetDouble(), 0, 100);
            result.BatteryLevel = (byte)Math.Round(percent / 10.0);
        }
        result.BatteryCharging = Bool(root, "charging");
        result.BatteryFull = Bool(root, "battery_full");
        result.MicMuted = Bool(root, "mic_muted");
        result.HeadphonesConnected = Bool(root, "headphones_connected");
        return result;
    }

    private static object ProfileInfo(HMProfile p) => new
    {
        id = p.Id,
        name = p.Name,
        displayName = p.DisplayName,
        vendor = p.Vendor,
        manufacturer = p.ManufacturerString,
        type = p.Type,
        connection = p.Connection,
        productString = p.ProductString,
        vendorId = p.VendorId,
        productId = p.ProductId,
        driverMode = p.DriverMode,
        backend = p.Backend,
        deployable = p.IsDeployable,
        buttons = p.ButtonCount,
        axes = p.AxisCount,
        availableAxes = p.AvailableAxes.Select(a => a.ToString()).ToArray(),
        sticks = p.StickCount,
        triggers = p.TriggerCount,
        triggerMode = p.TriggerMode,
        xinput = p.XInput != null || p.DriverMode == "xinputhid",
        requiresUsbip = p.RequiresUsbipBackend
    };

    private static object RunProfileSweep()
    {
        if (!IsElevated())
            throw new UnauthorizedAccessException("The profile sweep creates real Windows virtual devices. Run the elevated Controller Lab script and approve UAC.");
        if (!DriverPrepared)
            throw new InvalidOperationException("The pinned virtual driver is not prepared. Run the explicit driver setup first.");
        if (Controllers.Count != 0)
            throw new InvalidOperationException("Destroy active virtual slots before starting the profile sweep.");

        using var sample = JsonDocument.Parse("""
            {
              "buttons":["south","east","west","north","left_shoulder","right_shoulder","back","start"],
              "axes":{"left_x":0.35,"left_y":-0.55,"right_x":-0.25,"right_y":0.65,"left_trigger":0.72,"right_trigger":0.91},
              "dpad":["up","right"]
            }
            """);
        var candidates = Context!.AllProfiles
            .Where(p => p.IsDeployable && !p.RequiresUsbipBackend)
            .OrderBy(p => p.Type, StringComparer.OrdinalIgnoreCase)
            .ThenBy(p => p.Vendor, StringComparer.OrdinalIgnoreCase)
            .ThenBy(p => p.Id, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        var results = new List<object>();
        int passed = 0, failed = 0;
        for (int i = 0; i < candidates.Length; i++)
        {
            var profile = candidates[i];
            string message = "";
            try
            {
                using var virtualDevice = Context.CreateController(profile, "elmos-controller-lab/sweep/" + profile.Id);
                if (profile.Type.Contains("keyboard", StringComparison.OrdinalIgnoreCase))
                {
                    HMKey[] keys = { HMKey.A, HMKey.Enter };
                    virtualDevice.SubmitKeyboard(HMKeyModifiers.LeftShift, keys);
                }
                else if (profile.Type.Contains("mouse", StringComparison.OrdinalIgnoreCase))
                {
                    var mouse = new HMMouseState
                    {
                        Buttons = HMMouseButtons.Left | HMMouseButtons.Right,
                        X = 12, Y = -7, Wheel = 1, Pan = 0
                    };
                    virtualDevice.SubmitMouse(in mouse);
                }
                else
                {
                    var frame = BuildState(profile, sample.RootElement);
                    virtualDevice.SubmitState(in frame);
                }
                passed++;
                results.Add(new { id = profile.Id, name = profile.Name, type = profile.Type, status = "pass" });
                message = "pass";
            }
            catch (Exception ex)
            {
                failed++;
                results.Add(new { id = profile.Id, name = profile.Name, type = profile.Type,
                    status = "fail", error = ex.GetType().Name, message = ex.Message });
                message = "fail: " + ex.GetType().Name;
            }
            Emit(new { event_name = "sweep_progress", completed = i + 1,
                total = candidates.Length, profile = profile.Id, status = message });
        }

        var report = new
        {
            backend = "HIDMaestro",
            backendSdkVersion = BackendSdkVersion,
            createdUtc = DateTime.UtcNow,
            total = candidates.Length,
            passed,
            failed,
            skippedComposite = Context.AllProfiles.Count(p => p.IsDeployable && p.RequiresUsbipBackend),
            results
        };
        var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ElmosControllerLab", "reports");
        Directory.CreateDirectory(folder);
        var reportPath = Path.Combine(folder, "profile-sweep-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + ".json");
        File.WriteAllText(reportPath, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
        return new { total = candidates.Length, passed, failed, reportPath };
    }

    private static object ProbeWgi()
    {
        try
        {
            var devices = RawGameController.RawGameControllers;
            var result = devices.Select(device =>
            {
                var buttons = new bool[device.ButtonCount];
                var switches = new GameControllerSwitchPosition[device.SwitchCount];
                var axes = new double[device.AxisCount];
                var timestamp = device.GetCurrentReading(buttons, switches, axes);
                return new
                {
                    name = device.DisplayName,
                    vendorId = device.HardwareVendorId,
                    productId = device.HardwareProductId,
                    buttons = device.ButtonCount,
                    buttonsDown = buttons.Count(value => value),
                    axes = device.AxisCount,
                    axisValues = axes.Select(value => Math.Round(value, 4)).ToArray(),
                    switches = device.SwitchCount,
                    timestamp
                };
            }).ToArray();
            return new { available = true, devices = result };
        }
        catch (Exception ex)
        {
            return new { available = false, error = ex.GetType().Name, message = ex.Message, devices = Array.Empty<object>() };
        }
    }

    private static object Execute(JsonElement root)
    {
        var op = Text(root, "op", "") ?? "";
        switch (op)
        {
            case "hello":
                return new { version = "0.1.0", platform = Environment.OSVersion.ToString(),
                    elevated = IsElevated(), driverInstalled = Context!.IsDriverInstalled };
            case "wgi":
                return ProbeWgi();
            case "status":
                return new { elevated = IsElevated(), driverInstalled = Context!.IsDriverInstalled,
                    driverPrepared = DriverPrepared, backendSdkVersion = BackendSdkVersion,
                    profileCount = Context.AllProfiles.Count, activeControllers = Controllers.Count,
                    runtime = Environment.Version.ToString(), architecture = System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture.ToString() };
            case "profiles":
                return new { driverInstalled = Context!.IsDriverInstalled,
                    profiles = Context.AllProfiles.Select(ProfileInfo).ToArray() };
            case "install-driver":
                if (!IsElevated())
                    throw new UnauthorizedAccessException("Driver installation requires administrator approval. Close the lab and run Install-ControllerLab-Driver.ps1, then approve the Windows UAC prompt.");
                Context!.InstallDriver();
                if (!Context.IsDriverInstalled) throw new InvalidOperationException("The SDK returned, but Windows does not report the virtual driver as installed.");
                Directory.CreateDirectory(Path.GetDirectoryName(DriverStampPath)!);
                File.WriteAllText(DriverStampPath, BackendSdkVersion);
                return new { installed = Context.IsDriverInstalled, prepared = DriverPrepared,
                    backendSdkVersion = BackendSdkVersion, outcome = Context.LastDriverInstall?.ToString() ?? "checked" };
            case "create":
            {
                if (!IsElevated())
                    throw new UnauthorizedAccessException("Creating a virtual Windows controller requires administrator approval. Run the lab's elevated driver setup first.");
                var slot = Text(root, "slot", "virtual-0") ?? "virtual-0";
                var profileId = Text(root, "profile_id", "") ?? "";
                if (slot.Length is 0 or > 80) throw new ArgumentException("Invalid virtual slot.");
                if (Controllers.ContainsKey(slot)) throw new InvalidOperationException($"Slot '{slot}' already exists.");
                if (!Context!.IsDriverInstalled)
                    throw new InvalidOperationException("Virtual driver is not installed. Use the explicit Install driver action first.");
                if (!DriverPrepared)
                    throw new InvalidOperationException("The virtual driver has not been explicitly prepared for this SDK version. Run Install-ControllerLab-Driver.ps1 first; device creation will not install or upgrade drivers silently.");
                var profile = Context.GetProfile(profileId) ?? throw new ArgumentException($"Unknown virtual profile: {profileId}");
                if (!profile.IsDeployable) throw new InvalidOperationException($"Profile '{profileId}' is not deployable.");
                if (profile.RequiresUsbipBackend)
                    throw new NotSupportedException("This profile uses the separate composite USB/IP transport. It is listed for discovery but disabled in this first lab build until its extra installation and teardown workflow is implemented.");
                var controller = Context.CreateController(profile, "elmos-controller-lab/" + slot);
                controller.OutputDecoded += (_, e) => Emit(new { event_name = "output_decoded", slot, fields = e.Fields });
                controller.OutputReceived += (_, e) => Emit(new { event_name = "output_raw", slot, report_id = e.ReportId, data = Convert.ToBase64String(e.Data.ToArray()) });
                Controllers.Add(slot, controller);
                return new { created = true, slot, profile = ProfileInfo(profile), identity = controller.IdentityKey };
            }
            case "sweep":
                return RunProfileSweep();
            case "state":
            {
                var slot = Text(root, "slot", "virtual-0") ?? "virtual-0";
                if (!Controllers.TryGetValue(slot, out var controller))
                    throw new InvalidOperationException($"No virtual controller is active in slot '{slot}'.");
                var state = root.TryGetProperty("state", out var stateNode) ? stateNode : root;
                var frame = BuildState(controller.Profile, state);
                controller.SubmitState(in frame);
                return new { submitted = true, slot };
            }
            case "keyboard":
            {
                var slot = Text(root, "slot", "virtual-keyboard") ?? "virtual-keyboard";
                if (!Controllers.TryGetValue(slot, out var controller))
                    throw new InvalidOperationException($"No virtual keyboard is active in slot '{slot}'.");
                if (!controller.Profile.Type.Contains("keyboard", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException($"Slot '{slot}' is not a keyboard profile.");
                HMKeyModifiers modifiers = HMKeyModifiers.None;
                if (root.TryGetProperty("modifiers", out var modifierArray) && modifierArray.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in modifierArray.EnumerateArray())
                    {
                        if (item.ValueKind != JsonValueKind.String || !Enum.TryParse<HMKeyModifiers>(item.GetString(), true, out var modifier))
                            throw new ArgumentException("Unknown keyboard modifier.");
                        modifiers |= modifier;
                    }
                }
                var keys = new List<HMKey>();
                if (root.TryGetProperty("keys", out var keyArray) && keyArray.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in keyArray.EnumerateArray())
                    {
                        if (item.ValueKind != JsonValueKind.String || !Enum.TryParse<HMKey>(item.GetString(), true, out var key) || key == HMKey.None)
                            throw new ArgumentException("Unknown keyboard key.");
                        keys.Add(key);
                    }
                }
                controller.SubmitKeyboard(modifiers, keys.ToArray());
                return new { submitted = true, slot, keyCount = keys.Count };
            }
            case "mouse":
            {
                var slot = Text(root, "slot", "virtual-mouse") ?? "virtual-mouse";
                if (!Controllers.TryGetValue(slot, out var controller))
                    throw new InvalidOperationException($"No virtual mouse is active in slot '{slot}'.");
                if (!controller.Profile.Type.Contains("mouse", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException($"Slot '{slot}' is not a mouse profile.");
                HMMouseButtons buttons = HMMouseButtons.None;
                if (root.TryGetProperty("buttons", out var buttonArray) && buttonArray.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in buttonArray.EnumerateArray())
                    {
                        if (item.ValueKind != JsonValueKind.String || !Enum.TryParse<HMMouseButtons>(item.GetString(), true, out var button))
                            throw new ArgumentException("Unknown mouse button.");
                        buttons |= button;
                    }
                }
                var frame = new HMMouseState
                {
                    Buttons = buttons,
                    X = (int)Clamp(Number(root, "x"), -32768, 32767),
                    Y = (int)Clamp(Number(root, "y"), -32768, 32767),
                    Wheel = (int)Clamp(Number(root, "wheel"), -127, 127),
                    Pan = (int)Clamp(Number(root, "pan"), -127, 127)
                };
                controller.SubmitMouse(in frame);
                return new { submitted = true, slot };
            }
            case "destroy":
            {
                var slot = Text(root, "slot", "virtual-0") ?? "virtual-0";
                if (Controllers.Remove(slot, out var controller))
                {
                    controller.Dispose();
                    return new { destroyed = true, slot };
                }
                return new { destroyed = false, slot };
            }
            case "shutdown":
                foreach (var controller in Controllers.Values.ToArray())
                    try { controller.Dispose(); } catch { }
                Controllers.Clear();
                return new { shutdown = true };
            default:
                throw new ArgumentException("Unknown bridge operation: " + op);
        }
    }

    public static int Main(string[] args)
    {
        if (!OperatingSystem.IsWindows())
        {
            Console.Error.WriteLine("The virtual-device bridge is Windows-only.");
            return 2;
        }
        try
        {
            Context = new HMContext();
            var loaded = Context.LoadDefaultProfiles();
            if (args.Contains("--catalog-check"))
            {
                Emit(new { ok = loaded > 0, profiles = Context.AllProfiles.Count, deployable = Context.AllProfiles.Count(p => p.IsDeployable),
                    byType = Context.AllProfiles.GroupBy(p => p.Type).ToDictionary(g => g.Key, g => g.Count()) });
                Context.Dispose();
                Context = null;
                return loaded > 0 ? 0 : 4;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return 3;
        }

        try
        {
            string? line;
            while ((line = Console.ReadLine()) != null)
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                string? id = null;
                bool shouldExit = false;
                try
                {
                    using var document = JsonDocument.Parse(line);
                    var root = document.RootElement;
                    id = Text(root, "id");
                    var op = Text(root, "op", "") ?? "";
                    var result = Execute(root);
                    if (id != null) Emit(new { id, ok = true, result });
                    shouldExit = op == "shutdown";
                }
                catch (Exception ex)
                {
                    if (id != null) Emit(new { id, ok = false, error = ex.GetType().Name, message = ex.Message });
                    else Emit(new { event_name = "error", error = ex.GetType().Name, message = ex.Message });
                }
                if (shouldExit) break;
            }
        }
        finally
        {
            foreach (var controller in Controllers.Values.ToArray())
                try { controller.Dispose(); } catch { }
            Controllers.Clear();
            Context?.Dispose();
        }
        return 0;
    }
}
