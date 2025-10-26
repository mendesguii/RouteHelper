1. The Core Concept

A flight plan route is a sequence of geographical waypoints and airways connecting the departure and arrival airports.
It’s essentially a navigational “path” through the global airspace structure, defined by fixed routes (airways) and/or direct connections (DCTs) between points.

The purpose of route planning is to find the most efficient and permissible connection between origin and destination given current airspace rules, ATC preferences, and route availability.

2. How Route Generation Works
Step 1. Departure and Arrival Points

Every route starts and ends with:

SID (Standard Instrument Departure): predefined routes out of an airport toward the en-route airspace.

STAR (Standard Terminal Arrival Route): predefined routes bringing aircraft into the arrival airport from en-route airspace.

These are chosen based on:

The runway in use.

Direction of travel.

Airspace and noise restrictions.

So the route must connect:

[Airport] — SID — En-route airway network — STAR — [Airport]

Step 2. Build a Graph of Possible Paths

The world’s airspace is like a graph:

Nodes = Waypoints, navaids, intersections, fixes.

Edges = Airways connecting those waypoints (e.g., J575, Q41, UL602).

A flight planning system constructs a subgraph between the SID exit and STAR entry points using:

The current set of open airways.

Region-specific rules (altitude limits, directionality, traffic flow).

Step 3. Apply Routing Rules and Constraints

Now the system filters possible paths based on constraints such as:

Mandatory routing: e.g., Eurocontrol preferred routes or CDRs (Conditional Routes).

Directionality: some airways are one-way (eastbound/westbound).

Altitude constraints: certain airways are only usable above/below a given flight level.

Geopolitical limits: e.g., avoiding restricted, danger, or military areas.

Regional route availability: for example, NAT (North Atlantic) organized tracks that change daily.

This ensures the route is legal before optimization even begins.

Step 4. Generate Candidate Routes

The system now connects the SID exit point to the STAR entry point by:

Following existing airway structures.

Testing direct (DCT) segments where allowed by ATC or within Free Route Airspace (FRA).

Combining airway and direct segments — common in modern route planning.

It typically generates multiple “candidate” paths between origin and destination, all of which are valid under ATC and regulatory rules.

Step 5. Choose Between Airway and Direct Routing

Deciding when to skip airways and go “direct” depends on:

Free Route Airspace availability: In FRA regions (like most of Europe above FL195, or in the US above certain levels), aircraft can fly point-to-point without sticking to fixed airways.

ATC preferences: Some air traffic centers publish preferred entry/exit points between sectors — planners follow those to reduce the risk of rejection.

Traffic density: In quiet airspace (e.g., over the ocean, northern Canada, Africa), directs are common. In busy areas (central Europe), airway structures are preferred.

Route smoothness: A direct link that avoids multiple sharp turns, detours, or congested intersections may be prioritized.

Essentially, the system weighs whether skipping intermediate waypoints will simplify navigation without violating rules or entering prohibited airspace.

Step 6. Optimize the Path

Once multiple legal routes are available, the system uses an optimization algorithm (usually A*, Dijkstra, or a custom cost graph search) to find the shortest or most efficient path through the airspace network.

In pure routing terms, the optimization criterion is usually minimum track distance (great-circle distance adjusted for airway geometry and restrictions).

So the algorithm evaluates:

Great-circle distance between nodes.

Airway detours or route bends.

Route segment availability (open vs. closed).

Sector boundaries (to ensure smooth ATC handoff).

The final output is the shortest legal path that connects SID to STAR within the current airway network.

Step 7. Validation

The system then runs the chosen route through:

Route validation services (e.g., Eurocontrol IFPS, FAA preferred route database).

Crosschecks for discontinuities or conflicting segments.

Internal logic checks to ensure continuity between waypoints, FIR boundaries, and entry/exit points.

If rejected by ATC validation, the system automatically regenerates or adjusts the route to comply.

3. Example: Simplified Routing Logic

Let’s say you’re routing from London Heathrow (EGLL) to Istanbul (LTFM).

SID: DET2F (departure from runway 27R) ends at waypoint DET.

Available Airways: UL9, UL607, UN14, etc., connect across Europe.

Intermediate Waypoints: Frankfurt FIR → Vienna FIR → Sofia FIR.

STAR: OKTET1D into Istanbul.

The planner evaluates hundreds of combinations:

DET UL9 KONAN UL607 BATTY UN14 GONUP STAR


or

DET DCT KONAN DCT KOPOR UN14 GONUP STAR


and picks whichever satisfies route rules and offers the shortest navigational distance.

4. Modern Developments: Free Route and Dynamic Routing

In newer systems:

The traditional airway grid is being replaced by Free Route Airspace (FRA) concepts.

Within FRA, the system can directly connect any two points (waypoints, FIR entry/exit) as long as the path doesn’t cross restricted zones.

Over oceanic regions (e.g., North Atlantic), routes are based on daily dynamic tracks (NATs) optimized for prevailing winds, updated every 12 hours.

Thus, modern routes can look like:

NAT Track C: MALOT 51N020W 52N030W 53N040W 52N050W DORYY


or simply:

DCT MALOT DCT LULOX DCT


in areas with full free routing.

5. Summary of Route Logic
Phase	Description
Define Constraints	Load airway network, FIRs, closed areas, mandatory routes.
Generate Graph	Build nodes (waypoints) and edges (available airways/directs).
Find Candidates	Use SIDs/STARs to connect airports to the en-route structure.
Apply Rules	Filter for directionality, altitude, airspace restrictions.
Optimize Path	Compute shortest or smoothest route through the network.
Validate	Ensure route complies with ATC and regional rules.

In short:
Airline flight plan routes are created by algorithmically connecting departure and arrival procedures through a graph of airways and waypoints, pruning illegal or closed options, testing direct connections, and selecting the shortest valid path — or, in modern free-route systems, simply connecting key waypoints directly while respecting airspace boundaries.


---


# Understanding X-Plane Airways Data Lines

Each line in X-Plane’s **airways database (`earth_awy.dat`)** defines a single airway segment — essentially a connection between two fixes (waypoints or navaids) that belong to the same named airway.

Let’s break down one example and then apply it to the lines you posted.

---

## 1. General Format of an X-Plane Airway Line

The structure is:


| Field | Description |
|:------|:-------------|
| **fix1_id** | Identifier (name) of the first fix or navaid |
| **fix1_icao_country** | Two-letter country code (from ICAO prefix) |
| **fix1_type** | Fix type code (11 = waypoint, 2 = VOR, 3 = NDB, etc.) |
| **fix1_freq_or_0** | Frequency in MHz for navaids, or `0` for waypoints |
| **fix2_id** | Identifier of the second fix (the other end of the airway segment) |
| **fix2_icao_country** | Country code for the second fix |
| **fix2_type** | Fix type code for the second fix |
| **fix2_freq_or_0** | Frequency in MHz for navaids, or `0` for waypoints |
| **direction** | One-way or bidirectional indicator:<br>• `N` = two-way<br>• `P` = positive direction (fix1 → fix2)<br>• `M` = negative direction (fix2 → fix1) |
| **route_class** | Route classification:<br>• `1` = lower (domestic, below FL245)<br>• `2` = upper (above FL245) |
| **lower_alt** | Minimum altitude (hundreds of feet) at which the airway segment can be used |
| **upper_alt** | Maximum altitude (hundreds of feet) for the segment |
| **airway_name** | The name of the airway (e.g., B590, UR984, ATS14, etc.) |

---

## 2. Example Breakdown

### Example line:
07EBA DT 11 GILEX DT 11 N 1 95 245 G869


| Field | Value | Meaning |
|--------|--------|---------|
| fix1 | `07EBA` | First fix identifier |
| fix1_country | `DT` | Country code (Tunisia) |
| fix1_type | `11` | Waypoint |
| fix2 | `GILEX` | Second fix |
| fix2_country | `DT` | Same country (Tunisia) |
| fix2_type | `11` | Waypoint |
| direction | `N` | Both directions allowed |
| route_class | `1` | Lower airway |
| lower_alt | `95` | Minimum usable altitude FL095 |
| upper_alt | `245` | Maximum usable altitude FL245 |
| airway_name | `G869` | Airway identifier |

So this defines the airway **G869** segment between `07EBA` and `GILEX`, valid from **FL095 to FL245**, in **both directions**, for **lower airspace**.

---

## 3. Now decode all your examples

| Line | Explanation |
|------|--------------|
| `07EBA DT 11 GILEX DT 11 N 1  95 245 G869` | Waypoint **07EBA** ↔ **GILEX** in Tunisia; two-way, lower airway **G869**, usable FL095–FL245. |
| `26KIN FZ 11 DITRO FZ 11 N 1  40 245 ATS14` | Waypoint **26KIN** ↔ **DITRO** in Eswatini (FZ); bidirectional lower airway **ATS14**, FL040–FL245. |
| `26KIN FZ 11 KI452 FZ 11 N 1  40 245 ATS14` | Same region, another segment of airway **ATS14** connecting **26KIN–KI452**, same altitude limits. |
| `60VLI NF 11 KAPNO AG 11 N 1   0 600 B590` | Waypoints **60VLI (Norfolk Island)** ↔ **KAPNO (Antigua/AG)**; lower airway **B590**, FL000–FL600. |
| `60VLI NF 11 KAPNO AG 11 N 2   0 600 B590` | Same as above but **route class 2** (upper route version) — meaning the airway exists in both lower and upper airspace. |
| `61YCY CY 11 JULET CY 11 N 1  90 179 BR20` | Two-way segment **YCY–JULET** in Canada; lower airway **BR20**, usable FL090–FL179. |
| `62KGI FZ 11 EDLAM FZ 11 N 2 245 600 UR984` | Two-way segment **KGI–EDLAM** in Eswatini; upper airway **UR984**, FL245–FL600. |

---

## 4. Summary Interpretation Rules

- **Route class 1** → "Lower ATS route" (often prefixes like A, B, G, R).
- **Route class 2** → "Upper ATS route" (prefixes usually start with U or L, like UL602, UR984).
- **Altitude values** are in flight levels (hundreds of feet).
- **Direction** normally `N` (both ways), but `P` or `M` may restrict flow direction.
- Each pair of fixes defines a **segment** of an airway — the full airway is made of many such lines chained together.

---

**In short:**  
These lines in `earth_awy.dat` define the *connectivity and altitude limits* of each airway segment between pairs of waypoints, describing whether the airway is upper or lower, which country and fix types it involves, and at what flight levels it can be used.


# Understanding X-Plane Fix Data Lines (`earth_fix.dat`)

Each line in the **X-Plane `earth_fix.dat`** file defines a **navigation fix (waypoint)** — a precise latitude/longitude position used for routing (on airways or as standalone RNAV fixes).

These are used by the simulator and by the flight planning system to build the airway graph.

---

## 1. General Format

Each fix line has the structure:


…but in reality, only the first six fields are standardized and consistent across all data sources. The rest (numeric IDs, textual codes) can vary by dataset version.

A simplified generic breakdown (based on Laminar Research and Navigraph data formats):

| Field | Description |
|--------|-------------|
| **Latitude** | Geographic latitude in decimal degrees (north positive, south negative). |
| **Longitude** | Geographic longitude in decimal degrees (east positive, west negative). |
| **Fix Identifier** | The name or code of the fix (e.g., `07EBA`, `1630N`, `0515W`). |
| **Region / Usage** | “ENRT” = enroute fix (as opposed to terminal fix in an airport file). |
| **Country / FIR code** | ICAO country or FIR code (e.g., `DT` for Tunisia, `GV` for Cape Verde, `GO` for Senegal). |
| **Database ID** | An internal record number used by X-Plane / NavData providers (Jeppesen, Navigraph). |
| **Textual name** | Sometimes a reference name, such as a coordinate-style fix (`05S015W`) or a local waypoint name (`EBA357107`). |

---

## 2. Example Breakdown

### Line:
33.492513889 9.217400000 07EBA ENRT DT 2118994 EBA357107


| Field | Value | Meaning |
|--------|--------|---------|
| **Latitude** | 33.492513889 | Fix position (north of equator) |
| **Longitude** | 9.217400000 | East of Greenwich |
| **Fix ID** | `07EBA` | Fix identifier |
| **Region/Usage** | `ENRT` | Enroute fix |
| **Country Code** | `DT` | Tunisia (ICAO country prefix) |
| **Database ID** | `2118994` | Internal navdata record number |
| **Name/Label** | `EBA357107` | Internal or derived fix name (may include station and bearing info) |

This fix defines the geographical coordinates of the waypoint **07EBA** (used earlier in your airway file).

---
