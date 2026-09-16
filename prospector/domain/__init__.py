"""Dominio: entidades e regras puras, sem I/O."""
from prospector.domain.lead import Lead, LeadStatus, Region, region_from_source

__all__ = ["Lead", "LeadStatus", "Region", "region_from_source"]
