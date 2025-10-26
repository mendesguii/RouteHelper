from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class AiracCycle(Base):
    __tablename__ = "airac_cycles"
    id = Column(Integer, primary_key=True)
    cycle = Column(String(8), unique=True, index=True, nullable=False)  # e.g., '2510'
    name = Column(String(100), nullable=True)
    revision = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    current = Column(Boolean, default=False, nullable=False)


class Fix(Base):
    __tablename__ = "fixes"
    id = Column(Integer, primary_key=True)
    ident = Column(String(8), index=True, nullable=False)  # FIX ID (e.g., GILEX)
    usage = Column(String(16), nullable=True)  # ENRT or other
    country = Column(String(4), nullable=True)  # DT, CY, etc.
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    dbid = Column(String(32), nullable=True)
    name = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("ident", "country", "lat", "lon", name="uq_fix_ident_country_coords"),
        Index("ix_fix_ident_country", "ident", "country"),
    )


class Airport(Base):
    __tablename__ = "airports"
    id = Column(Integer, primary_key=True)
    icao = Column(String(8), unique=True, index=True, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    country = Column(String(4), nullable=True)


class Airway(Base):
    __tablename__ = "airways"
    id = Column(Integer, primary_key=True)
    name = Column(String(16), index=True, nullable=False)  # e.g., UL607
    # segment endpoints are Fix references; country is included in lookup key via Fix.country
    fix1_id = Column(Integer, ForeignKey("fixes.id"), nullable=False)
    fix2_id = Column(Integer, ForeignKey("fixes.id"), nullable=False)
    direction = Column(String(1), nullable=False)  # 'N', 'P', 'M'
    route_class = Column(Integer, nullable=False)  # 1 lower, 2 upper
    lower_fl = Column(Integer, nullable=False)
    upper_fl = Column(Integer, nullable=False)

    fix1 = relationship("Fix", foreign_keys=[fix1_id])
    fix2 = relationship("Fix", foreign_keys=[fix2_id])

    __table_args__ = (
        Index("ix_airway_name", "name"),
        Index("ix_airway_fix_pair", "fix1_id", "fix2_id"),
    )


class FlightPlan(Base):
    __tablename__ = "flight_plans"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    origin = Column(String(8), index=True, nullable=False)
    dest = Column(String(8), index=True, nullable=False)
    aircraft = Column(String(32), nullable=True)
    fl_start = Column(Integer, nullable=True)
    fl_end = Column(Integer, nullable=True)
    cycle = Column(String(8), nullable=True)
    route_text = Column(Text, nullable=True)
    route_list = Column(Text, nullable=True)  # space-joined tokens
    sid_text = Column(Text, nullable=True)
    star_text = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_fpl_origin_dest", "origin", "dest"),
    )


class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    icao = Column(String(8), index=True, nullable=False)
    proc_type = Column(String(8), index=True, nullable=False)  # 'SID' | 'STAR'
    name = Column(String(64), index=True, nullable=False)
    start = Column(String(32), nullable=True)  # initial fix/transition start
    route = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("icao", "proc_type", "name", "start", name="uq_proc_key"),
        Index("ix_proc_icao_type_name", "icao", "proc_type", "name"),
    )
