// Best-effort browser geolocation capture for geo-fencing-gated actions (Create Lead,
// Verify Documents). Never throws and never blocks a form on failure — permission
// denied/unavailable/timeout/no-API-support all resolve to `null`, which the backend
// treats as "no coordinates supplied": harmless if no Geo Fence is configured for that
// activity, or a clear rejection if one is (see app/features/geo_fencing/enforcement.py).
// Backend is authoritative either way — this is purely a convenience for the common case.

export interface Coordinates {
  latitude: number;
  longitude: number;
}

const TIMEOUT_MS = 8000;

export function getCurrentCoordinates(): Promise<Coordinates | null> {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
      () => resolve(null), // permission denied, position unavailable, or timeout
      { enableHighAccuracy: true, timeout: TIMEOUT_MS, maximumAge: 0 },
    );
  });
}
