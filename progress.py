#!/usr/bin/env python3
"""
Sistema de reporte de progreso mejorado
"""
import time
from typing import Optional
from colorama import Fore, Style
from utils import format_size, format_time


class ProgressTracker:
    """Seguimiento de progreso con estadísticas en tiempo real"""

    def __init__(self, total_files: int, operation_name: str = "Procesando"):
        self.total_files = total_files
        self.operation_name = operation_name
        self.start_time = time.time()
        self.current_index = 0

        # Contadores
        self.processed = 0
        self.successful = 0
        self.duplicates = 0
        self.errors = 0
        self.skipped = 0

        # Para cálculo de velocidad
        self.bytes_processed = 0
        self.last_update_time = time.time()

    def update(
        self,
        filename: str,
        status: str = 'processing',
        file_size: Optional[int] = None,
        upload_time: Optional[float] = None
    ):
        """Actualizar progreso con nuevo archivo"""
        self.current_index += 1

        # Calcular progreso
        progress_pct = (self.current_index / self.total_files * 100) if self.total_files > 0 else 0
        elapsed = time.time() - self.start_time

        # Calcular ETA
        if self.current_index > 0 and self.total_files > 0:
            avg_time_per_file = elapsed / self.current_index
            remaining_files = self.total_files - self.current_index
            eta = remaining_files * avg_time_per_file
            eta_str = format_time(eta)
        else:
            eta_str = "calculando..."

        # Calcular velocidad si hay tamaño de archivo
        speed_str = ""
        if file_size and upload_time and upload_time > 0:
            speed_mbps = (file_size / upload_time / 1024 / 1024)
            speed_str = f" - {speed_mbps:.2f}MB/s"
            self.bytes_processed += file_size

        # Mensaje de estado
        status_msg = f"{Fore.CYAN}⏳ Procesando{Style.RESET_ALL}"
        if status == 'success':
            status_msg = f"{Fore.GREEN}✅ Éxito{Style.RESET_ALL}"
        elif status == 'duplicate':
            status_msg = f"{Fore.YELLOW}⚠ Duplicado{Style.RESET_ALL}"
        elif status == 'error':
            status_msg = f"{Fore.RED}❌ Error{Style.RESET_ALL}"
        elif status == 'skipped':
            status_msg = f"{Fore.YELLOW}⏭ Saltado{Style.RESET_ALL}"

        # Imprimir progreso
        print(f"\r{' ' * 120}", end='', flush=True)  # Limpiar línea
        print(
            f"\r[{self.current_index}/{self.total_files}] ({progress_pct:.1f}%) "
            f"ETA: {eta_str} - {status_msg} - {filename[:50]}{speed_str}",
            end='',
            flush=True
        )

    def increment_counter(self, counter_name: str):
        """Incrementar un contador específico"""
        if counter_name == 'processed':
            self.processed += 1
        elif counter_name == 'successful':
            self.successful += 1
        elif counter_name == 'duplicates':
            self.duplicates += 1
        elif counter_name == 'errors':
            self.errors += 1
        elif counter_name == 'skipped':
            self.skipped += 1

    def print_summary(self):
        """Imprimir resumen final"""
        total_time = time.time() - self.start_time
        avg_speed = self.processed / total_time if total_time > 0 else 0

        print("\n\n" + "=" * 60)
        print(f"{Fore.CYAN}RESUMEN DEL PROCESO{Style.RESET_ALL}")
        print("=" * 60)
        print(f"Archivos procesados:      {self.processed}")
        print(f"{Fore.GREEN}✅ Subidas exitosas:      {self.successful}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}⚠  Duplicados:             {self.duplicates}{Style.RESET_ALL}")
        print(f"⏭  Saltados (ya subidos):  {self.skipped}")
        print(f"{Fore.RED}❌ Errores:               {self.errors}{Style.RESET_ALL}")
        print("-" * 60)
        print(f"Tiempo total:             {format_time(total_time)}")
        print(f"Velocidad promedio:       {avg_speed:.2f} archivos/s")

        if self.bytes_processed > 0:
            print(f"Datos transferidos:       {format_size(self.bytes_processed)}")
            throughput = self.bytes_processed / total_time if total_time > 0 else 0
            print(f"Throughput promedio:      {format_size(throughput)}/s")

        print("=" * 60 + "\n")
