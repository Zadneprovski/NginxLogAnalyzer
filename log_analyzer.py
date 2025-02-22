import argparse
import gzip
import json
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime
from string import Template
from typing import List, Optional

import structlog

# Дефолтный конфиг
DEFAULT_CONFIG = {"REPORT_SIZE": 10, "REPORT_DIR": "./reports", "LOG_DIR": "./log"}

# Логирование
logger = structlog.get_logger()


def setup_logging(log_file: Optional[str] = None):
    processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]

    if log_file:
        structlog.configure(
            processors=processors,
            logger_factory=structlog.PrintLoggerFactory(
                file=open(log_file, "a", encoding="utf-8")
            ),
        )
    else:
        structlog.configure(
            processors=processors, logger_factory=structlog.PrintLoggerFactory()
        )


# Структура данных для логов
class LogEntry:
    def __init__(self, url: str, request_time: float):
        self.url = url
        self.request_time = request_time

    def __repr__(self):
        return f"LogEntry(url={self.url}, request_time={self.request_time})"


# Функция загрузки конфигурации из JSON
def load_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        logger.error(f"Config file '{config_path}' not found.")
        raise FileNotFoundError(f"Config file '{config_path}' not found.")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Config file '{config_path}' is not a valid JSON.")
        raise ValueError(f"Config file '{config_path}' is not a valid JSON.")

    # Слияние с дефолтным конфигом, приоритет у загруженного
    merged_config = {**DEFAULT_CONFIG, **file_config}
    return merged_config


# Функция для поиска последнего лог-файла
def find_last_log(log_dir: str, pattern: str) -> Optional[str]:
    files = [f for f in os.listdir(log_dir) if re.match(pattern, f)]
    if not files:
        logger.info("No log files found.")
        return None
    last_log = max(
        files,
        key=lambda f: (
            datetime.strptime(re.match(pattern, f).group(1), "%Y%m%d")
            if re.match(pattern, f)
            else ""
        ),
    )
    return os.path.join(log_dir, last_log)


# Функция для парсинга логов
def parse_log_file(file_path: str) -> List[LogEntry]:
    log_entries = []

    # Регулярки для парсинга URL и времени
    url_pattern = r'"(?:GET|POST|PUT|DELETE) (/[^"]+)"'
    time_pattern = r"(\d+\.\d+)$"

    # Открываем файл логов (сжаты или обычные)
    with gzip.open(file_path, "rt", encoding="utf-8") as log_file:
        for line in log_file:
            # Ищем URL
            url_match = re.search(url_pattern, line)
            if url_match:
                url = url_match.group(1)  # URL находится в 1-й группе

            # Ищем время запроса
            time_match = re.search(time_pattern, line)
            if time_match:
                request_time = float(time_match.group(1))  # Время запроса в 1-й группе

                # Добавляем результат в список
                log_entries.append(LogEntry(url, request_time))

    return log_entries


# Функция для генерации отчета
def generate_report(log_entries: list, report_dir: str, report_size: int):
    # Убедимся, что директория для отчетов существует, если нет, создадим ее
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    url_stats: defaultdict[str, dict[str, float | list[float]]] = defaultdict(
        lambda: {"count": 0, "time_sum": 0.0, "request_times": []}
    )

    for entry in log_entries:
        url_stats[entry.url]["count"] += 1
        url_stats[entry.url]["time_sum"] += entry.request_time
        url_stats[entry.url]["request_times"].append(entry.request_time)

    total_count = sum(float(stats["count"]) for stats in url_stats.values())
    total_time = sum(float(stats["time_sum"]) for stats in url_stats.values())

    sorted_urls = sorted(
        url_stats.items(), key=lambda x: x[1]["time_sum"], reverse=True
    )[:report_size]

    # Преобразуем статистику в формат для шаблона
    table_json = json.dumps(
        [
            {
                "count": stats["count"],
                "time_avg": (
                    sum(stats["request_times"]) / len(stats["request_times"])
                    if len(stats["request_times"]) > 0
                    else 0
                ),
                "time_max": (
                    max(stats["request_times"]) if stats["request_times"] else 0
                ),
                "time_sum": stats["time_sum"],
                "url": url,
                "time_med": (
                    statistics.median(stats["request_times"])
                    if stats["request_times"]
                    else 0
                ),
                "time_perc": (
                    (stats["time_sum"] / total_time) * 100 if total_time else 0
                ),
                "count_perc": (
                    (stats["count"] / total_count) * 100 if total_count else 0
                ),
            }
            for url, stats in sorted_urls
        ]
    )

    # Создание отчета
    date_str = datetime.now().strftime("%Y.%m.%d")
    report_path = os.path.join(report_dir, f"report-{date_str}.html")

    with open("report.html", "r", encoding="utf-8") as template_file:
        template = Template(template_file.read())
    report_content = template.safe_substitute(table_json=table_json)

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(report_content)

    logger.info(f"Report generated: {report_path}")


# Основной процесс
def main():
    parser = argparse.ArgumentParser(description="Log Analyzer")
    parser.add_argument(
        "--config", type=str, default="config.json", help="Path to configuration file"
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)

        setup_logging(config.get("LOG_FILE"))

        # Определим шаблон для логов
        log_pattern = r"nginx-access-ui.log-(\d{8})\.gz"

        last_log = find_last_log(config["LOG_DIR"], log_pattern)

        if not last_log:
            logger.info("No log files found. Exiting.")
            return

        log_entries = parse_log_file(last_log)
        generate_report(log_entries, config["REPORT_DIR"], config["REPORT_SIZE"])

    except KeyboardInterrupt:
        logger.error("Process interrupted by user (Ctrl+C). Exiting.", exc_info=True)
    except Exception:
        logger.error("Unexpected error occurred.", exc_info=True)


if __name__ == "__main__":
    main()
