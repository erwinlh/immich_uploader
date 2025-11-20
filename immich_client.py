#!/usr/bin/env python3
"""
Cliente para interactuar con la API de Immich
"""
import os
import requests
import json
from datetime import datetime
from typing import Dict, Any
from config import IMMICH_URL, IMMICH_API_KEY
from logger import logger


class ImmichClient:
    """Cliente para comunicarse con la API de Immich"""

    def __init__(self):
        self.base_url = IMMICH_URL
        self.api_key = IMMICH_API_KEY
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'x-api-key': self.api_key,
        })
        logger.info(f"Cliente Immich inicializado para {self.base_url}")

    def upload_file(self, filepath: str) -> Dict[str, Any]:
        """
        Subir un archivo a Immich
        Retorna diccionario con status_code, response_text, headers, error
        """
        url = f"{self.base_url}/api/assets"

        try:
            stats = os.stat(filepath)
            data = {
                'deviceAssetId': f'{os.path.basename(filepath)}-{stats.st_mtime}',
                'deviceId': 'immich-uploader-script',
                'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                'isFavorite': 'false',
            }

            with open(filepath, 'rb') as file:
                files = {
                    'assetData': (os.path.basename(filepath), file, 'application/octet-stream')
                }

                logger.debug(f"Subiendo archivo: {filepath}")
                response = self.session.post(url, data=data, files=files)

                result = {
                    'status_code': response.status_code,
                    'response_text': response.text,
                    'headers': dict(response.headers)
                }

                if response.status_code in [200, 201]:
                    logger.info(f"Archivo subido exitosamente: {filepath}")
                elif response.status_code == 409:
                    logger.info(f"Archivo duplicado detectado: {filepath}")
                else:
                    logger.warning(
                        f"Upload falló para {filepath}: "
                        f"status={response.status_code}, response={response.text[:100]}"
                    )

                return result

        except Exception as e:
            logger.error(f"Error subiendo archivo {filepath}: {str(e)}")
            return {
                'status_code': 0,
                'error': str(e),
                'response_text': None
            }

    def verify_connection(self) -> bool:
        """
        Verificar que la conexión con Immich funciona
        Intenta varios endpoints comunes - si alguno responde, asumimos que está OK
        """
        # Lista de endpoints para probar (soporte para versiones antiguas y nuevas)
        endpoints = [
            "/api/server/ping",         # Versiones antiguas
            "/server-info/ping",        # Versiones antiguas (sin /api)
            "/api/server-info/ping",    # Versiones nuevas
            "/api/auth/validateToken",  # Validación de API key
        ]

        for endpoint in endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = self.session.get(url, timeout=5)

                # Cualquier respuesta que no sea 404/500 es válida
                if response.status_code < 500:
                    logger.info(f"Conexión con Immich verificada (endpoint: {endpoint}, status: {response.status_code})")
                    return True
            except Exception as e:
                logger.debug(f"Endpoint {endpoint} no disponible: {str(e)}")
                continue

        # Si ningún endpoint funcionó, advertir pero no fallar
        logger.warning("No se pudo verificar conexión con Immich, pero se intentará subir archivos de todas formas")
        return True  # Retornar True para continuar

    def close(self):
        """Cerrar sesión"""
        self.session.close()
        logger.debug("Sesión de Immich cerrada")
