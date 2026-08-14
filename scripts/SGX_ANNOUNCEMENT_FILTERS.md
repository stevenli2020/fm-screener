# SGX Announcement URL Filter Reference

This document records the SGX Company Announcements URL protocol and the M4 category
selection policy verified on 13 August 2026.

## URL format

Base URL:

```text
https://www.sgx.com/stock-exchange/company-announcements
```

Supported query parameters observed on the SGX page:

| Parameter | Meaning | Format |
| --- | --- | --- |
| `pagesize` | Results displayed per page | `100` |
| `page` | Result page number | `1`, `2`, ... |
| `from` | Inclusive start date | `YYYYMMDD` |
| `to` | Inclusive end date | `YYYYMMDD` |
| `value` | Exact SGX autocomplete selection | URL-encoded company/security name |
| `type` | Autocomplete result class | `company` or `security` |
| `ANNC` | Announcement category codes | Comma-separated codes |
| `CACT` | Corporate Action category codes | Comma-separated codes |
| `PLST` | Product Announcements & Listings codes | Comma-separated codes |
| `TRAD` | Trading Status category codes | Comma-separated codes |

Multiple category codes are separated by commas. An encoded comma appears as `%2C`.
The displayed dropdown order does not follow code-number order, so use the explicit mappings
below rather than deriving a code from an item's position.

When filters or dates change, start with page 1. If the result count exceeds 100, append
`&page=2`, `&page=3`, and so on.

## Company and security filter protocol

The **Filter by Company/Security Name** control adds two parameters after an item is
selected from the autocomplete list:

```text
value=<exact SGX displayed name>&type=<company|security>
```

For example, selecting the SGX company `DBS BANK LTD.` for 11-12 August 2026 produces:

```text
https://www.sgx.com/stock-exchange/company-announcements?pagesize=100&value=DBS%20BANK%20LTD.&type=company&from=20260811&to=20260812
```

Important distinctions:

- `value` must be the exact name returned and selected from SGX autocomplete, not arbitrary
  free text.
- `type=company` identifies a company/issuer result.
- `type=security` identifies a listed-security result.
- Spaces and punctuation in `value` must be URL encoded.
- The D05 universe mapping is `DBS GROUP HOLDINGS LTD`. `DBS BANK LTD.` is a different SGX
  issuer selection and is retained above only as the observed protocol example.
- Ordinary shares normally use `type=company`. REITs, trusts, and ETFs in the mapping use
  `type=security` because the selected identity is the listed security name.
- Company/security filtering can be combined with dates, category parameters, page size,
  and pagination.

The machine-readable mapping for the next extractor version is stored in
`sgx_announcement_filters.json` in this directory.

## M4 category policy

`Keep*` means conditionally relevant to bonds, funds, REITs, or another affected instrument.
Conditional categories remain enabled for the current M4 policy.

### Announcements (`ANNC`)

| Code | Selectable item | Policy |
| --- | --- | --- |
| `ANNC01` | Amendment to Articles | Drop |
| `ANNC02` | Announcement in Relation to Regulatory Actions by SGX and/or Other Authorities | Keep |
| `ANNC03` | Announcement of Appointment | Keep |
| `ANNC04` | Announcement of Cessation | Keep |
| `ANNC05` | Annual General Meeting | Drop |
| `ANNC30` | Annual Reports and Related Documents | Keep |
| `ANNC06` | Asset Acquisitions and Disposals | Keep |
| `ANNC07` | Asset Securitisation | Keep* |
| `ANNC31` | Bond Holder's Meeting | Keep* |
| `ANNC29` | Change in capital | Keep |
| `ANNC08` | Change in Corporate Information | Drop |
| `ANNC09` | Change in Issuer Name | Drop |
| `ANNC10` | Change in Trading Currency | Drop |
| `ANNC11` | Change of Catalist Sponsor | Drop |
| `ANNC12` | Court Meeting | Keep* |
| `ANNC14` | Disclosure of Interest/Changes in Interest | Keep |
| `ANNC15` | Employee Stock Option/Share Scheme | Keep |
| `ANNC16` | Extraordinary/Special General Meeting | Keep |
| `ANNC17` | Financial Statements | Keep |
| `ANNC18` | General Announcement | Keep |
| `ANNC19` | Interested Person Transaction | Keep |
| `ANNC20` | Moratorium | Keep |
| `ANNC21` | Notice of 3 Consecutive Years' Losses | Keep |
| `ANNC22` | Notice of Valuation of Real Assets | Keep* |
| `ANNC23` | Placements | Keep |
| `ANNC24` | Regulatory Actions by SGX | Keep |
| `ANNC25` | Response to SGX Queries | Keep |
| `ANNC13` | Share Buy Back-On Market | Keep |
| `ANNC26` | Share Purchase Mandate | Keep |
| `ANNC27` | Tender/Acquisition/Takeover/Purchase Offer | Keep |
| `ANNC28` | Waiver | Keep* |

Summary: 25 kept, 6 dropped.

### Corporate Action (`CACT`)

| Code | Selectable item | Policy |
| --- | --- | --- |
| `CACT22` | Bondholder's Early Redemption (Put Option) | Keep* |
| `CACT01` | Bonus Issue/Capitalisation Issue | Keep |
| `CACT02` | Capital Distribution | Keep |
| `CACT03` | Capital Gains Distribution | Keep* |
| `CACT04` | Capital Reduction | Keep |
| `CACT06` | Cash Dividend/Distribution | Keep |
| `CACT24` | Conversion | Keep |
| `CACT07` | Corporate Debt Restructuring | Keep |
| `CACT25` | Coupon Payment | Keep* |
| `CACT08` | Dividend/Distribution paid in Scrip/Unit | Keep |
| `CACT09` | Dividend/Distribution Reinvestment | Keep |
| `CACT05` | Exchange Offer/Capital Reorganisation | Keep |
| `CACT10` | Final Maturity | Keep* |
| `CACT23` | Issuer's Early Redemption (Call Option) | Keep* |
| `CACT11` | Liquidation Dividend/Distribution/Liquidation Payment | Keep |
| `CACT12` | Merger | Keep |
| `CACT13` | Other Scheme of Arrangement | Keep |
| `CACT14` | Pari-Passu for Security with different ranking | Drop* |
| `CACT15` | Partial Redemption with reduction of nominal value | Keep* |
| `CACT16` | Repurchase Offer/Issuer Bid/Reverse Rights | Keep |
| `CACT18` | Rights | Keep |
| `CACT19` | Scrip Election/Distribution/DRP | Keep |
| `CACT17` | Share Consolidation | Keep |
| `CACT20` | Spin-Off/Demerger | Keep |
| `CACT21` | Stock Split/Subdivision | Keep |

Summary: 24 kept, 1 dropped.

### Product Announcements & Listings (`PLST`)

| Code | Selectable item | Policy |
| --- | --- | --- |
| `PLST01` | Change of Terms | Drop* |
| `PLST03` | Listing Confirmation | Drop |
| `PLST05` | Listing-Equity | Drop |
| `PLST06` | Listing-Exchange Traded Products | Drop |
| `PLST07` | Listing-Other Products | Drop |
| `PLST08` | Listing-Warrants | Drop |
| `PLST09` | Outstanding Position Reporting | Drop |
| `PLST10` | Warrant Exercise | Drop |

Summary: 0 kept, 8 dropped. The `PLST` parameter is therefore omitted from the M4 URL.

### Trading Status (`TRAD`)

| Code | Selectable item | Policy |
| --- | --- | --- |
| `TRAD08` | Buying-In | Keep |
| `TRAD09` | Delisting of Security | Keep |
| `TRAD01` | Designated Market Maker (DMM) Obligations | Drop |
| `TRAD02` | Query Regarding Trading Activity | Keep |
| `TRAD03` | Request for Lifting of Trading Halt | Keep |
| `TRAD04` | Request for Resumption of Trading from Suspension | Keep |
| `TRAD05` | Request for Suspension | Keep |
| `TRAD06` | Request for Trading Halt | Keep |
| `TRAD10` | Transfer from Catalist to Mainboard | Drop |
| `TRAD11` | Transfer from Mainboard to Catalist | Drop |
| `TRAD12` | Transfer from Primary to Secondary Listing | Drop |
| `TRAD13` | Transfer from Secondary to Primary Listing | Drop |

Summary: 7 kept, 5 dropped.

## Overall selection

| Group | Kept | Dropped | Total |
| --- | ---: | ---: | ---: |
| Announcements | 25 | 6 | 31 |
| Corporate Action | 24 | 1 | 25 |
| Product Announcements & Listings | 0 | 8 | 8 |
| Trading Status | 7 | 5 | 12 |
| **Total** | **56** | **20** | **76** |

## Example: 11-12 August 2026

The following URL selects all 56 kept categories for the inclusive period from 11 to
12 August 2026 and requests up to 100 listing rows:

```text
https://www.sgx.com/stock-exchange/company-announcements?pagesize=100&from=20260811&to=20260812&ANNC=ANNC02%2CANNC03%2CANNC04%2CANNC30%2CANNC06%2CANNC07%2CANNC31%2CANNC29%2CANNC12%2CANNC14%2CANNC15%2CANNC16%2CANNC17%2CANNC18%2CANNC19%2CANNC20%2CANNC21%2CANNC22%2CANNC23%2CANNC24%2CANNC25%2CANNC13%2CANNC26%2CANNC27%2CANNC28&CACT=CACT22%2CCACT01%2CCACT02%2CCACT03%2CCACT04%2CCACT06%2CCACT24%2CCACT07%2CCACT25%2CCACT08%2CCACT09%2CCACT05%2CCACT10%2CCACT23%2CCACT11%2CCACT12%2CCACT13%2CCACT15%2CCACT16%2CCACT18%2CCACT19%2CCACT17%2CCACT20%2CCACT21&TRAD=TRAD08%2CTRAD09%2CTRAD02%2CTRAD03%2CTRAD04%2CTRAD05%2CTRAD06
```

## Intended M4 request order

1. Build a short inclusive date window.
2. Apply the kept category codes in the listing-page URL.
3. Request 100 rows per listing page.
4. Match listing rows against M3 candidates, portfolio holdings, and the watch list.
5. Open only matched announcement detail pages.
6. Download attachments only when required for research.

This policy reduces SGX requests while retaining announcement types that may explain or
materially affect a screened security.
