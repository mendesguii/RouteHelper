from datetime import datetime


def build_vatsim_icao_fpl(
    *,
    callsign: str,
    actype: str,
    wakecat: str,
    equipment: str,
    surveillance: str,
    dep_icao: str,
    dep_time: str,
    speed: str,
    level: str,
    route: str,
    dest_icao: str,
    eet: str,
    endurance_hhmm: str = '',
    alt1: str = '',
    alt2: str = '',
    pbn: str = '',
    nav: str = '',
    rnp: str = '',
    dof: str = '',
    reg: str = '',
    sel: str = '',
    code: str = '',
    rvr: str = '',
    opr: str = '',
    per: str = '',
    rmk: str = '',
) -> str:
    """Compose the ICAO FPL message as multiline, mirroring the working example.

    Notes:
    - Endurance removed per request.
    - RNP token is `RNP{rnp}`.
    - All optional tokens consolidated on the last line.
    """
    lines: list[str] = []
    lines.append(f"(FPL-{callsign}-IS")
    lines.append(f"-{actype}/{wakecat}-{equipment}{surveillance}")
    lines.append(f"-{dep_icao}{dep_time}")
    route_part = (" " + route.strip()) if route and route.strip() else ""
    lines.append(f"-{speed}{level}{route_part}")
    alt1_part = f" {alt1.strip()}" if alt1 and alt1.strip() else ""
    alt2_part = f" {alt2.strip()}" if alt2 and alt2.strip() else ""
    lines.append(f"-{dest_icao}{eet}{alt1_part}{alt2_part}")
    other_tokens: list[str] = []
    if pbn: other_tokens.append(f"PBN/{pbn}")
    if nav: other_tokens.append(f"NAV/{nav}")
    if rnp: other_tokens.append(f"RNP{rnp}")
    if dof: other_tokens.append(f"DOF/{dof}")
    if reg: other_tokens.append(f"REG/{reg}")
    if sel: other_tokens.append(f"SEL/{sel}")
    if code: other_tokens.append(f"CODE/{code}")
    if rvr: other_tokens.append(f"RVR/{rvr}")
    if opr: other_tokens.append(f"OPR/{opr}")
    if per: other_tokens.append(f"PER/{per}")
    if rmk: other_tokens.append(f"RMK/{rmk}")
    if other_tokens:
        lines.append("-" + " ".join(other_tokens))
    lines[-1] = lines[-1] + ")"
    return "\n".join(lines)
