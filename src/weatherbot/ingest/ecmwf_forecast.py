"""Cron entrypoint for the ECMWF variant of open_meteo_forecast.run() - see
that module's docstring for what this actually does and why."""

from weatherbot.ingest.open_meteo_forecast import run

if __name__ == "__main__":
    run("ECMWF")
