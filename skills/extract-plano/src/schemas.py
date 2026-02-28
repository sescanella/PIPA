"""
Pydantic models for validated extraction data from technical drawing PDFs.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class MaterialRow(BaseModel):
    item: int
    diam: Optional[str] = None
    codigo: Optional[str] = None
    descripcion: Optional[str] = None
    cantidad: Optional[str] = None
    n_colada: Optional[str] = None


class SoldaduraRow(BaseModel):
    n_sold: int
    diam: Optional[str] = None
    tipo_sold: Optional[str] = None
    wps: Optional[str] = None
    fecha_soldadura: Optional[str] = None
    soldador: Optional[str] = None
    fecha_insp_visual: Optional[str] = None
    resultado_insp_visual: Optional[str] = None


class CorteRow(BaseModel):
    n_corte: Optional[str] = None
    diam: Optional[str] = None
    largo: Optional[str] = None
    extremo1: Optional[str] = None
    extremo2: Optional[str] = None


class CajetinData(BaseModel):
    model_config = {"populate_by_name": True}

    ot: Optional[str] = None
    of_: Optional[str] = Field(None, alias="of")
    tag_spool: Optional[str] = None
    diametro_pulgadas: Optional[str] = None
    cliente: Optional[str] = None
    cliente_final: Optional[str] = None
    linea: Optional[str] = None


class SpoolRecord(BaseModel):
    pdf_name: str
    status: str = "ok"              # "ok" | "partial" | "error"
    low_confidence: bool = False    # True if any region could not be read
    errors: List[str] = []          # Details of errors encountered
    cajetin: CajetinData
    materiales: List[MaterialRow] = []
    soldaduras: List[SoldaduraRow] = []
    cortes: List[CorteRow] = []
