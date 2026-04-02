from __future__ import annotations
from src.models.parse_result import ParseResult
from src.post_processors.metadata_enricher import MetadataEnricher
from src.post_processors.table_normaliser import TableNormaliser
from src.post_processors.image_extractor import ImageExtractor


class PostProcessingPipeline:
    @staticmethod
    def run(result: ParseResult) -> ParseResult:
        # Strict order: metadata -> structure (implicit) -> tables -> images -> final normalization
        result = MetadataEnricher.run(result)
        result = TableNormaliser.run(result)
        result = ImageExtractor.run(result)
        # Final normalization pass could add additional steps if needed
        result = MetadataEnricher.run(result)
        return result
