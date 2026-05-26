import logging
import os
from datetime import datetime, timezone

from elasticsearch import helpers
from elasticsearch.helpers import BulkIndexError
from tika import parser

from app.config import INDEX_NAME, TIKA_ENDPOINT, es
from app.services.document_db import update_document_status_in_background
from app.services.document_storage import save_document_to_storage

logger = logging.getLogger("app.services.pdf_ingest")


def _format_bulk_errors(errors: list) -> str:
    if not errors:
        return "Elasticsearch bulk indexing failed."

    first = errors[0]
    for _op, item in first.items():
        err = item.get("error")
        if isinstance(err, dict):
            reason = err.get("reason") or err.get("type") or str(err)
            status = item.get("status")
            if status:
                return f"Elasticsearch bulk error (HTTP {status}): {reason}"
            return f"Elasticsearch bulk error: {reason}"
        if err:
            return f"Elasticsearch bulk error: {err}"
        return f"Elasticsearch bulk error: {item}"

    return f"{len(errors)} document(s) failed to index in Elasticsearch."


def _bulk_index_pages(actions: list) -> tuple[int, list]:
    """
    Index pages via Elasticsearch bulk API.
    Returns (success_count, errors). Raises on connection/transport failures.
    """
    try:
        # Extract and print the connection details
        # 1. Safely extract URLs from the active node configs
        print(f"checcckkkkkkkkkkkk")
        print(f"es.transport: {es.transport}")
        # -------------------------------------------------------------
        # 1. VERSION-PROOF EXTRACTION OF TARGET URLS
        # -------------------------------------------------------------
        extracted_urls = []

        # Strategy A: Check modern _node_configs
        if hasattr(es.transport, '_node_configs'):
            print(f"Strategy A: _node_configs")
        #    extracted_urls = [str(config.base_url) for config in es.transport._node_configs]

        # Strategy B: Check older / async connection pool lists
        elif hasattr(es.transport, 'node_pool') and hasattr(es.transport.node_pool, '_all_nodes'):
            print(f"Strategy B: node_pool")
            print(f"es.transport.node_pool: {es.transport.node_pool}")
            print(f"es.transport.node_pool._all_nodes: {es.transport.node_pool._all_nodes}")
        #    extracted_urls = [str(node.base_url) for node in es.transport.node_pool._all_nodes]
            print(f"extracted_urls: {extracted_urls}")

        # Strategy C: Check the raw HTTP connection targets (v7.x style fallback)
        elif hasattr(es.transport, 'connection_pool'):
            print(f"Strategy C: connection_pool")
        #    extracted_urls = [str(conn.host) for conn in es.transport.connection_pool.connections]

        # Strategy D: Fallback directly to the initial meta properties
        elif hasattr(es, '_meta_info'):            
            print("Meta fallback triggered.")

        if extracted_urls:
            print(f"Target URLs: {extracted_urls}")
        else:
            print("Could not find internal URLs. Resorting to Transport string representation:")
            print(f"-> {es.transport}")


        # -------------------------------------------------------------
        # 2. EXTRACT API KEY FROM AUTHORIZATION HEADER
        # -------------------------------------------------------------
        #headers = es.transport.headers
        #auth_header = headers.get("authorization", "")

        print(f"check API KEY")

        #if auth_header and auth_header.startswith("ApiKey "):
        #    api_key = auth_header.replace("ApiKey ", "").strip()
        #    print(f"API Key found: {api_key}")
        #else:
        #    print("No API Key found in headers (check your auth settings).")

        print(f"go to ping")    

        if es.ping():
            print("Connection is OK! Elasticsearch cluster is reachable.")
            
            # 2. (Optional) Print cluster info to verify details
            info = es.info()
            print(f"Cluster Name: {info['cluster_name']}")
            print(f"ES Version: {info['version']['number']}")
        else:
            print("Connection failed. es.ping() returned False.")

        
        success_count, errors = helpers.bulk(
            es,
            actions,
            raise_on_error=False,
        )
        return success_count, errors if isinstance(errors, list) else []
    except BulkIndexError as e:
        return 0, e.errors


def process_and_index_pdf(file_path: str, document_id: str, original_filename: str):
    """Heavy OCR and Elasticsearch ingestion task run in the background."""
    try:
        logger.info(
            "[1/6] Background task started document_id=%s file=%s",
            document_id,
            file_path,
        )

        headers = {
            "X-Tika-PDFOcrStrategy": "no_ocr",
            "X-Tika-PDFextractInlineImages": "false",
            "X-Tika-OCRmaxFileSizeToOcr": "0",
        }

        logger.info("[2/6] Calling Tika at %s", TIKA_ENDPOINT)
        raw = parser.from_file(
            file_path, serverEndpoint=TIKA_ENDPOINT, headers=headers
        )
        content = raw.get("content", "")
        pages = content.split("\f")
        logger.info(
            "[3/6] Tika finished document_id=%s pages_split=%s content_len=%s",
            document_id,
            len(pages),
            len(content),
        )

        actions = []
        page_num = 1
        date = datetime.now(timezone.utc).isoformat()

        for page_text in pages:
            cleaned_text = page_text.strip()
            if not cleaned_text:
                continue

            actions.append(
                {
                    "_index": INDEX_NAME,
                    "_source": {
                        "document_id": document_id,
                        "publish_date": date,
                        "filename": original_filename,
                        "page_number": page_num,
                        "content": cleaned_text,
                    },
                }
            )
            page_num += 1

        #print(f"actions: {actions}") 
        #logger.info(f"actions: {actions}")   

        if not actions:
            update_document_status_in_background(
                document_id,
                "failed",
                error_message="No indexable page content extracted from PDF.",
            )
            logger.warning(
                "[STOP] No indexable pages document_id=%s file=%s",
                document_id,
                file_path,
            )
            return

        logger.info(
            "[4/6] Elasticsearch bulk start document_id=%s pages=%s index=%s",
            document_id,
            len(actions),
            INDEX_NAME,
        )
        success_count, errors = _bulk_index_pages(actions)
        logger.info(
            "[4/6] Elasticsearch bulk done document_id=%s success=%s errors=%s",
            document_id,
            success_count,
            len(errors),
        )

        if errors or success_count < len(actions):
            update_document_status_in_background(
                document_id,
                "failed",
                error_message=_format_bulk_errors(errors),
            )
            logger.error(
                "[STOP] Bulk failed document_id=%s %s/%s succeeded",
                document_id,
                success_count,
                len(actions),
            )
            return

        stored_path = save_document_to_storage(
            file_path, document_id, original_filename or ""
        )
        logger.info(
            "[5/6] Document saved to storage document_id=%s path=%s",
            document_id,
            stored_path,
        )

        update_document_status_in_background(
            document_id,
            "indexed",
            page_count=success_count,
        )
        logger.info(
            "[6/6] Complete document_id=%s indexed_pages=%s",
            document_id,
            success_count,
        )

    except Exception as e:
        update_document_status_in_background(
            document_id,
            "failed",
            error_message=str(e),
        )
        logger.exception("[STOP] Error document_id=%s", document_id)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("Temp file removed: %s", file_path)
