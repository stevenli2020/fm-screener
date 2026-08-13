# M2 — SGX universe closure

Approved by the user on 2026-08-12.

- Validated and loaded 42 SGX securities into SQLite using the independent project data server.
- Persisted coverage metadata (bar count, dates, adjusted-price contract and candle-repair count).
- Added eligibility policy: 120-bar minimum, at most five repairs, three-day freshness, adjusted prices only; ETFs excluded and REITs use initial equity thresholds.

No changes were made to `D:\Projects\mh_test`.
