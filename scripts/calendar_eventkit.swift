// Native Calendar adapter. Input and output are JSON; event data never enters shell source.
import Foundation
import EventKit
import AppKit

let args = CommandLine.arguments
let requestPath = args.firstIndex(of: "--request").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
let outputPath = args.firstIndex(of: "--output").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
func emit(_ value: [String: Any]) {
    let bytes = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    if let path = outputPath { try! bytes.write(to: URL(fileURLWithPath: path), options: .atomic); return }
    FileHandle.standardOutput.write(bytes)
    FileHandle.standardOutput.write(Data("\n".utf8))
}
func fail(_ reason: String) -> Never { emit(["status": "failed", "error": reason]); exit(1) }
let input = requestPath.flatMap { try? Data(contentsOf: URL(fileURLWithPath: $0)) } ?? FileHandle.standardInput.readDataToEndOfFile()
let parsed = (try? JSONSerialization.jsonObject(with: input)) as? [String: Any]
guard let req = parsed ?? (input.isEmpty ? ["action": "authorize"] : nil) else { fail("invalid_json") }
let store = EKEventStore()
let action = req["action"] as? String ?? "probe"
if action == "authorize" {
    let application = NSApplication.shared
    application.setActivationPolicy(.accessory)
    application.activate(ignoringOtherApps: true)
    var finished = false
    store.requestFullAccessToEvents { _, _ in finished = true }
    let deadline = Date().addingTimeInterval(60)
    while !finished && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
}
guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else { fail("calendar_full_access_required") }
let iso = ISO8601DateFormatter()
func date(_ value: Any?) -> Date? { return (value as? String).flatMap { iso.date(from: $0) } }
func calendars() -> [[String: Any]] {
    return store.calendars(for: .event).map { ["id": $0.calendarIdentifier, "name": $0.title,
        "writable": $0.allowsContentModifications, "source_type": $0.source.sourceType.rawValue] }
}
if action == "probe" || action == "authorize" {
    emit(["status": "ready", "calendars": calendars()]); exit(0)
}
if action == "ensure_calendar" {
    guard let name = req["calendar"] as? String, !name.isEmpty else { fail("invalid_calendar") }
    let existing = store.calendars(for: .event).filter { $0.title == name }
    if existing.count == 1 { emit(["status": "ready", "calendar_id": existing[0].calendarIdentifier]); exit(0) }
    guard existing.isEmpty, let source = store.defaultCalendarForNewEvents?.source,
          source.sourceType != .local else { fail("no_unique_synced_calendar_source") }
    let c = EKCalendar(for: .event, eventStore: store); c.title = name; c.source = source
    do { try store.saveCalendar(c, commit: true) } catch { fail("calendar_creation_failed") }
    emit(["status": "ready", "calendar_id": c.calendarIdentifier]); exit(0)
}
if action == "cleanup_verification" {
    guard let eid = req["event_id"] as? String,
          let event = store.calendarItem(withIdentifier: eid) as? EKEvent,
          event.title == "Obsidian Calendar Bridge verification",
          event.url?.scheme == "obsidian-assistant", event.url?.host == "calendar-request" else { fail("not_verification_event") }
    do { try store.remove(event, span: .thisEvent, commit: true) } catch { fail("verification_cleanup_failed") }
    emit(["status": "removed"]); exit(0)
}
if action == "snapshot" {
    guard let start = date(req["start"]), let end = date(req["end"]), end > start else { fail("invalid_window") }
    let cals = store.calendars(for: .event)
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: cals)
    let events = store.events(matching: predicate).map { e -> [String: Any] in
        return ["native_id": e.calendarItemIdentifier, "occurrence_start": iso.string(from: e.startDate),
            "calendar_id": e.calendar.calendarIdentifier, "calendar": e.calendar.title,
            "start_at": iso.string(from: e.startDate), "end_at": iso.string(from: e.endDate),
            "title": e.title ?? "", "is_allday": e.isAllDay, "is_cancelled": e.status == .canceled]
    }
    emit(["schema_version": 1, "complete": true, "captured_at": iso.string(from: Date()),
          "window_start": iso.string(from: start), "window_end": iso.string(from: end),
          "calendars": calendars(), "events": events]); exit(0)
}
if action == "create" {
    guard let start = date(req["start"]), let end = date(req["end"]), end > start,
          let title = req["title"] as? String, !title.isEmpty,
          let rid = req["request_id"] as? String, rid.count == 64,
          rid.allSatisfy({ $0.isHexDigit }), let calName = req["calendar"] as? String else { fail("invalid_request") }
    let matches = store.calendars(for: .event).filter { $0.calendarIdentifier == calName || $0.title == calName }
    guard matches.count == 1, let calendar = matches.first else { fail("calendar_missing_or_ambiguous") }
    guard calendar.allowsContentModifications else { fail("calendar_read_only") }
    let marker = URL(string: "obsidian-assistant://calendar-request/" + rid)!
    let predicate = store.predicateForEvents(withStart: start.addingTimeInterval(-1), end: end.addingTimeInterval(1), calendars: [calendar])
    let previous = store.events(matching: predicate).filter { $0.url == marker }
    if let e = previous.first {
        emit(["status": "created", "event_id": e.calendarItemIdentifier, "deduplicated": true]); exit(0)
    }
    // A lost response / crashed worker is reconciled read-only. Never replay an uncertain write.
    guard req["allow_create"] as? Bool == true else {
        emit(["status": "outcome_unknown", "error": "prior_attempt_requires_reconciliation"]); exit(0)
    }
    let event = EKEvent(eventStore: store)
    event.calendar = calendar; event.title = title; event.startDate = start; event.endDate = end
    event.notes = req["notes"] as? String; event.location = req["location"] as? String; event.url = marker
    do { try store.save(event, span: .thisEvent, commit: true) }
    catch { emit(["status": "outcome_unknown", "error": "native_save_failed"]); exit(1) }
    guard let saved = store.calendarItem(withIdentifier: event.calendarItemIdentifier) as? EKEvent,
          saved.url == marker, saved.title == title,
          abs(saved.startDate.timeIntervalSince(start)) < 1,
          abs(saved.endDate.timeIntervalSince(end)) < 1 else {
        emit(["status": "outcome_unknown", "error": "readback_failed"]); exit(1)
    }
    emit(["status": "created", "event_id": saved.calendarItemIdentifier, "deduplicated": false]); exit(0)
}
fail("unsupported_action")
