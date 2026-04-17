# CLAUDE.md — civio-app

## Scope
This is the **resident-facing Flutter mobile app** for iOS and Android. Residents use it to register their SIP endpoint, place and receive calls, manage friends, view announcements, and top up their token balance.

## Tech stack (pinned)

```yaml
environment:
  sdk: ">=3.5.0 <4.0.0"
  flutter: ">=3.24.0"

dependencies:
  flutter:
    sdk: flutter

  # State management
  flutter_riverpod: ^2.6.1
  riverpod_annotation: ^2.6.1

  # Networking
  dio: ^5.7.0
  retrofit: ^4.4.1
  json_annotation: ^4.9.0

  # SIP / media
  sip_ua: ^0.7.2
  flutter_webrtc: ^0.11.7

  # Native call UI + push
  flutter_callkit_incoming: ^2.0.4
  firebase_core: ^3.6.0
  firebase_messaging: ^15.1.3

  # Storage
  drift: ^2.20.3
  sqlite3_flutter_libs: ^0.5.24
  flutter_secure_storage: ^9.2.2
  path_provider: ^2.1.4

  # Audio / permissions
  audio_session: ^0.1.21
  permission_handler: ^11.3.1
  wakelock_plus: ^1.2.8

  # Routing
  go_router: ^14.6.2

  # i18n
  flutter_localizations:
    sdk: flutter
  intl: ^0.19.0

  # Utilities
  freezed_annotation: ^2.4.4
  logger: ^2.4.0

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^5.0.0
  build_runner: ^2.4.13
  riverpod_generator: ^2.6.3
  retrofit_generator: ^9.1.5
  json_serializable: ^6.8.0
  freezed: ^2.5.7
  drift_dev: ^2.20.3
  mocktail: ^1.0.4
  integration_test:
    sdk: flutter
```

## Architecture

Clean Architecture, 4 layers. Strict dependency direction: presentation → domain → data → platform.

```
lib/
├── main.dart                       entry, ProviderScope wrapping App
├── app.dart                        MaterialApp with go_router
├── core/
│   ├── network/
│   │   ├── dio_provider.dart
│   │   ├── auth_interceptor.dart   attaches JWT, retries on 401
│   │   └── api_exception.dart
│   ├── sip/
│   │   ├── sip_client.dart         SipClient wrapping SipUaHelper
│   │   ├── sip_config.dart
│   │   ├── call_controller.dart
│   │   └── sip_event_bus.dart
│   ├── push/
│   │   ├── push_handler.dart       FCM + PushKit unified
│   │   ├── callkit_bridge.dart
│   │   └── incoming_call_dispatcher.dart
│   ├── storage/
│   │   ├── app_database.dart       drift
│   │   ├── secure_storage.dart
│   │   └── daos/
│   ├── di/
│   │   └── providers.dart          top-level Riverpod providers
│   ├── routing/
│   │   └── router.dart             go_router configuration
│   ├── theme/
│   │   ├── app_theme.dart
│   │   └── colors.dart
│   ├── i18n/
│   │   ├── strings_en.arb
│   │   ├── strings_zh_TW.arb
│   │   ├── strings_zh_CN.arb
│   │   └── strings_vi.arb
│   └── utils/
│       └── logger.dart
├── features/
│   ├── auth/
│   │   ├── presentation/
│   │   │   ├── login_screen.dart
│   │   │   ├── otp_screen.dart
│   │   │   └── providers/
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   ├── repositories/       abstract class AuthRepository
│   │   │   └── use_cases/
│   │   │       ├── send_otp_use_case.dart
│   │   │       ├── verify_otp_use_case.dart
│   │   │       └── logout_use_case.dart
│   │   └── data/
│   │       ├── auth_repository_impl.dart
│   │       ├── auth_remote_data_source.dart    retrofit API
│   │       └── auth_local_data_source.dart     secure_storage
│   ├── call/
│   │   ├── presentation/
│   │   │   ├── dialer_screen.dart
│   │   │   ├── in_call_screen.dart
│   │   │   ├── incoming_call_screen.dart
│   │   │   └── providers/
│   │   ├── domain/
│   │   │   ├── entities/call.dart
│   │   │   ├── repositories/call_repository.dart
│   │   │   └── use_cases/
│   │   │       ├── make_call_use_case.dart
│   │   │       ├── answer_call_use_case.dart
│   │   │       └── hangup_call_use_case.dart
│   │   └── data/
│   │       └── sip_ua_call_repository.dart
│   ├── contacts/
│   ├── wallet/
│   ├── messaging/
│   └── settings/
└── shared/
    ├── widgets/
    └── errors/
```

## Core class contracts

### `core/sip/sip_client.dart`

```dart
class SipClient {
  SipClient(this._helper);
  final SipUaHelper _helper;

  Future<void> init(SipConfig config);
  Future<void> register();
  Future<void> unregister();
  Future<Call> makeCall(String targetUri, {bool videoEnabled = false});
  Stream<RegistrationState> registrationState$;
  Stream<Call> incomingCalls$;
}
```

### `core/sip/call_controller.dart`

```dart
class CallController {
  CallController(this._call, this._callKit);
  final Call _call;
  final CallKitBridge _callKit;

  Future<void> answer();
  Future<void> hangup();
  Future<void> mute(bool enabled);
  Future<void> setSpeakerphone(bool enabled);
  Stream<CallState> state$;
  Duration get currentDuration;
}
```

### `core/push/callkit_bridge.dart`

```dart
class CallKitBridge {
  Future<void> init();

  /// On iOS, MUST be called within milliseconds of PushKit delivery
  /// or the app will be killed by the OS.
  Future<void> showIncomingCall(IncomingCallPayload payload);
  Future<void> endCall(String callId);

  Stream<CallKitAction> actions$;
}
```

### `features/call/domain/repositories/call_repository.dart`

```dart
abstract class CallRepository {
  Future<void> register();
  Future<Call> makeCall(String targetUri);
  Future<void> answer(Call call);
  Future<void> hangup(Call call);
  Stream<CallState> watchCallState();
  Stream<Call> watchIncomingCalls();
}
```

## State management (Riverpod 2.x)

Use `riverpod_generator` for all providers.

```dart
@riverpod
SipClient sipClient(SipClientRef ref) => ...;

@riverpod
Stream<CallState> callState(CallStateRef ref) {
  return ref.watch(callRepositoryProvider).watchCallState();
}

@riverpod
class CallController extends _$CallController {
  @override
  CallState build() => const CallState.idle();

  Future<void> makeCall(String uri) async { ... }
  Future<void> hangup() async { ... }
}
```

**Rule:** Every provider has a corresponding test in `test/providers/`.

## Push notification flow

### iOS (PushKit + CallKit)

1. Register for VoIP push in `AppDelegate.swift`
2. Cloud sends VoIP push → iOS delivers to app (even if killed)
3. In `pushRegistry(_:didReceiveIncomingPushWith:...)`, **immediately** call `reportNewIncomingCall` with CallKit — this is a hard OS requirement
4. Flutter side receives the action via `flutter_callkit_incoming`
5. App registers SIP, answers the pending INVITE

### Android (FCM + ConnectionService)

1. FCM high-priority data message → `FcmService`
2. Service starts `Foreground` + shows full-screen intent notification
3. User taps accept → app launches into `IncomingCallScreen`
4. SIP registers, answers the INVITE

**Never** use FCM notification messages for calls — they are deprioritised on Doze mode.

## Testing

```
test/
├── core/
│   ├── sip/
│   └── push/
├── features/
│   ├── auth/
│   │   └── domain/use_cases/
│   └── call/
│       └── domain/use_cases/
├── providers/
└── widget/
integration_test/
├── login_flow_test.dart
├── place_call_test.dart
└── receive_call_test.dart
```

- Unit tests cover every use case and repository
- Widget tests cover every screen
- Integration tests cover the three critical flows: login, outgoing call, incoming call
- Mock SIP server for integration tests: a small Python SIPp harness in `test/fixtures/`

### Verification

```bash
dart format --set-exit-if-changed lib/ test/
dart analyze --fatal-infos lib/ test/
flutter test --coverage
flutter test integration_test  # requires device/simulator
```

Coverage target: `>= 70%` (mobile UI code is harder to cover exhaustively).

## Constraints specific to Flutter app

- NEVER call `sip_ua` APIs directly from widgets. Always go through a UseCase.
- NEVER store the SIP password in shared preferences. Only `flutter_secure_storage`.
- NEVER log SIP URIs or JWT tokens at any level above `debug`.
- NEVER ignore `prefers-reduced-motion` for call UI animations.
- NEVER block the UI thread on network. All API calls are async.
- NEVER use `setState` for SIP state. Use Riverpod.
- NEVER bypass `go_router`. All navigation goes through typed routes.
- ALWAYS handle the case where microphone permission is denied.
- ALWAYS handle the case where push notification permission is denied — fall back to "keep app open" messaging.
