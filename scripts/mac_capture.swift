// Collect application transitions and heartbeats without screen capture or keystrokes.
import AppKit
import CoreGraphics
import Foundation

let args = CommandLine.arguments
guard args.count >= 3, let interval = Double(args[2]), interval >= 1 else { exit(2) }
let directory = URL(fileURLWithPath: args[1], isDirectory: true)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                       attributes: [.posixPermissions: 0o700])
let workspace = NSWorkspace.shared
let sessionID = UUID().uuidString
var awake = true
var sessionActive = true
let formatter = ISO8601DateFormatter()
formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
func capture(_ reason: String) {
    let app = workspace.frontmostApplication
    let row: [String: Any] = ["id": UUID().uuidString, "session_id": sessionID,
        "ts": formatter.string(from: Date()), "kind": reason,
        "app": app?.localizedName ?? "", "bundle_id": app?.bundleIdentifier ?? "",
        "idle_sec": CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .null),
        "awake": awake, "session_active": sessionActive, "source": "mac_native_v1"]
    do {
        let data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
        let file = directory.appendingPathComponent("\(row["id"]!).json")
        try data.write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
    } catch {
        // Fail visibly; launchd restarts us instead of silently losing further events.
        fputs("mac_capture_write_failed\n", stderr)
        exit(1)
    }
}
var observers: [NSObjectProtocol] = []
let notifications: [(Notification.Name, String)] = [
    (NSWorkspace.didActivateApplicationNotification, "app_changed"),
    (NSWorkspace.willSleepNotification, "sleep"),
    (NSWorkspace.didWakeNotification, "wake"),
    (NSWorkspace.sessionDidResignActiveNotification, "session_inactive"),
    (NSWorkspace.sessionDidBecomeActiveNotification, "session_active")]
for (name, reason) in notifications {
    observers.append(workspace.notificationCenter.addObserver(forName: name, object: nil, queue: .main) { _ in
        if reason == "sleep" { awake = false }
        if reason == "wake" { awake = true }
        if reason == "session_inactive" { sessionActive = false }
        if reason == "session_active" { sessionActive = true }
        capture(reason)
    })
}
capture("start")
if args.contains("--once") { exit(0) }
let timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { _ in capture("heartbeat") }
RunLoop.main.run()
