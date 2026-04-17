# civio-app

Flutter mobile app for residents. iOS + Android.

## Before touching this directory

**Read `CLAUDE.md` in this folder first.**

## Quick reference

```bash
# Install deps
flutter pub get

# Generate code (Riverpod, freezed, drift, retrofit)
dart run build_runner build --delete-conflicting-outputs

# Run on attached device/simulator
flutter run

# Test
flutter test
flutter test --coverage
flutter test integration_test    # requires device

# Lint + analyze
dart format --set-exit-if-changed lib/ test/
dart analyze --fatal-infos lib/ test/
```

## Architecture

Clean Architecture, 4 layers:

```
lib/
├── main.dart
├── app.dart
├── core/              infrastructure (sip, push, storage, network, di)
├── features/          one folder per feature, each with presentation/domain/data
└── shared/            cross-cutting widgets and utilities
```

State managed with **Riverpod 2.x** (code-generated providers).

## Further reading

- `/docs/01-architecture.md`
- `/docs/03-api-contract.yaml`
