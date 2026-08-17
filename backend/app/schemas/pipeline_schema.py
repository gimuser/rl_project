from pydantic import BaseModel, ConfigDict

class PipelineStats(BaseModel):
    total_rows: int
    total_columns: int
    missing_values: int

    model_config = ConfigDict(from_attributes=True)

class PipelineImportResponse(BaseModel):
    message: str
    imported_count: int

    model_config = ConfigDict(from_attributes=True)