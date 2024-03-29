"""Support for the EauFrance service."""
from datetime import datetime, timedelta, time
import pytz
import logging
import ast
from typing import Any, Dict, Mapping, Optional

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_NAME,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
)

from homeassistant.core import HomeAssistant
#from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
# from homeassistant.helpers.typing import (
#    ConfigType,
#    DiscoveryInfoType,
#    HomeAssistantType,
#    )
from homeassistant.util import Throttle
from homeassistant.util import dt as dt_util

import requests

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by {0}"

DEFAULT_NAME = "VC"

MIN_TIME_BETWEEN_UPDATES = timedelta(hours=1)

DEVICE_CLASS = {
    "H": "Height",
    "Q": "Flow",
}


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_DEVICE_ID, default=""): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(DEVICE_CLASS),
    }
)


async def async_setup_platform(hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback, discovery_info=None) -> None:
    #session = async_get_clientsession(hass)
    name = config.get(CONF_NAME)
    device_class = config.get(CONF_DEVICE_CLASS)
    device_id = config.get(CONF_DEVICE_ID)

    efd = EauFranceData(hass, device_id, device_class)
    async_add_entities(
        [VigicruesSensor.current(name, efd)],
        True,
    )


class EauFranceData():
    pass


class VigicruesSensor(Entity):
    """Implementation of an EauFrance sensor."""

    def __init__(self, name: str, efd: EauFranceData) -> None:
        """Initialize the sensor."""
        self._name = name
        self._efd = efd
        self._state = None
        self._unit_of_measurement = ""
        self._unique_id = efd.unique_id
        self._attributes = {
            "unique_id": self._unique_id,
            ATTR_ATTRIBUTION: ATTRIBUTION.format("EauFrance"),
        }

    @classmethod
    def current(cls, name: str, efd: EauFranceData):
        return cls(name, efd)

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return self._unit_of_measurement

    @property
    def icon(self) -> str:
        if self._efd.device_class == "H":
            return "mdi:waves"
        return "mdi:fast-forward"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return self._attributes

    def update(self) -> None:
        """Get the latest data from EauFrance and updates the state."""

        # try:
        self._efd.update(self.hass)
        # except:
        #    _LOGGER.error("Exception when getting EauFrance web update data")
        #    return

        self._state = self._efd.data
        self._unit_of_measurement = self._efd.unit


class EauFranceData():
    """Get the latest data from EauFrance.
    device_class must be H or Q
    """

    def __init__(self, hass: HomeAssistant, device_id: str, device_class: str) -> None:
        self._device_id = device_id
        self._device_class = device_class
        self._time_zone = hass.config.time_zone
        self.data = None

        if device_class == "H":
            self.unit = "m"
        else:
            self.unit = "m³/s"

    @property
    def device_class(self) -> str:
        return self._device_class

    @property
    def unique_id(self) -> str:
        return "edf_{}_{}".format(self._device_id, self._device_class)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self, hass: HomeAssistant) -> None:
        # get readings from eurfrance website
        try:
            obs = self.get_first_reading()

            if obs is None:
                _LOGGER.warning("Failed to fetch data from EauFrance")
                return

            if "resultat_obs" not in obs:
                _LOGGER.warning("resultat_obs not found in:")
                _LOGGER.warning(obs)

            self.data = obs["resultat_obs"] / 1000

            # show under 10m in cm, otherwise to 1 dp.
            if self.data < 10.0:
                self.data = round(self.data, 2)
            else:
                self.data = round(self.data, 1)

        except ConnectionError:
            _LOGGER.warning("Unable to connect to EauFrance URL")
        except TimeoutError:
            _LOGGER.warning("Timeout connecting to EauFrance URL")
        except Exception as e:
            _LOGGER.warning(
                "{0} occurred in update. Details: {1}".format(e.__class__, e))

    def get_device_history_url(self) -> str:
        """
        Create url to get the last 4h of readings for this station
        Parameters
            device_id   
        see
        https://hubeau.eaufrance.fr/page/api-hydrometrie#/hydrometrie/observations
        """

        # example https://hubeau.eaufrance.fr/api/v1/hydrometrie/observations_tr?code_entite=O588251001&grandeur_hydro=Q&timestep=60&sort=desc&date_debut_obs=2021-02-16

        base_url = "https://hubeau.eaufrance.fr/api/v1/hydrometrie/observations_tr"
        # sort so the most recent is first - only need to read the first result
        params = {
            "code_entite": self._device_id,
            "grandeur_hydro": self._device_class,
            "timestep": "60",
            "sort": "desc"
        }

        now_utc = dt_util.utcnow()
        start_of_period = now_utc - \
            timedelta(hours=2)    # get 4 hours readings
        params.update(
            {"date_debut_obs": start_of_period.strftime("%Y-%m-%dT%H:%M:%S")})

        #now = datetime.now()
        #_LOGGER.warning("now          : {0}".format(now.strftime("%Y-%m-%dT%H:%M:%S")))
        #_LOGGER.warning("utc          : {0}".format(now_utc.strftime("%Y-%m-%dT%H:%M:%S")))
        #_LOGGER.warning("startofperiod: {0}".format(start_of_period.strftime("%Y-%m-%dT%H:%M:%S")))

        all_params = '&'.join('{0}={1}'.format(key, val)
                              for key, val in params.items())

        return base_url + "?" + all_params

    def get_results_data(self):
        """
        Return the array of readings
        """
        url = self.get_device_history_url()
        response = requests.get(url)
        if response.status_code != requests.codes.ok:
            raise Exception("requests: getting data: {0}\n{1}\n{2}".format(
                response.status_code, url, response.content))
        content = response.content.decode()
        # returned example (split to ned lines for readability - no line breaks in reality)
        # after the date_obs and resultat_obs values
        #content = '{"count":10,"first":"https://hubeau.eaufrance.fr/api/v1/hydrometrie/observations_tr?code_entite=O588251001&grandeur_hydro=Q&timestep=60&sort=desc&date_debut_obs=2021-02-16&page=1&size=10","prev":null,"next":null,"api_version":"1.0.1","data":[{"code_site":"O5882510","code_station":"O588251001","grandeur_hydro":"Q","date_debut_serie":"2021-02-16T00:00:00Z","date_fin_serie":"2021-02-16T10:00:00Z","statut_serie":4,"code_systeme_alti_serie":31,"date_obs":"2021-02-16T10:00:00Z","resultat_obs":147629.0,"code_methode_obs":12,"libelle_methode_obs":"Interpolation","code_qualification_obs":16,"libelle_qualification_obs":"Non qualifiée","continuite_obs_hydro":true,"longitude":1.340482605,"latitude":44.091553707}]}'
        # content = '{
        # "count":10,
        # "first":"https://hubeau.eaufrance.fr/api/v1/hydrometrie/observations_tr?code_entite=O588251001&grandeur_hydro=Q&timestep=60&sort=desc&date_debut_obs=2021-02-16&page=1&size=10",
        # "prev":null,
        # "next":null,
        # "api_version":"1.0.1",
        # "data":[
        #   {"code_site":"O5882510",
        #   "code_station":"O588251001",
        #   "grandeur_hydro":"Q",
        #   "date_debut_serie":"2021-02-16T00:00:00Z",
        #   "date_fin_serie":"2021-02-16T10:00:00Z",
        #   "statut_serie":4,"code_systeme_alti_serie":31,
        #   "date_obs":"2021-02-16T10:00:00Z",
        #   "resultat_obs":147629.0,
        #   "code_methode_obs":12,
        #   "libelle_methode_obs":"Interpolation",
        #   "code_qualification_obs":16,
        #   "libelle_qualification_obs":"Non qualifiée",
        #   "continuite_obs_hydro":true,
        #   "longitude":1.340482605,
        #   "latitude":44.091553707
        #   }
        # <more data>
        # ]}'

        # not true python dictionary so need to reformat slightly
        content = content.replace(":null", ":None")
        content = content.replace(":true", ":True")

        root = ast.literal_eval(content)
        if "data" not in root:
            _LOGGER.warning(root)
            raise Exception("data not found in root")

        count = root["count"]
        if count == 0:
            raise Exception(
                "No observations returned for {0}".format(self._device_id))

        d = root["data"]
        if len(d) == 0:
            _LOGGER.warning(root)
            raise Exception("data contains no readings")
        return d

    def get_first_reading(self) -> Dict[str, str]:
        """
        Extract data_obs and resultat_obs from the first reading as this is the most up to date reading available
        return
        dictionary with these two key/values
        """
        d = self.get_results_data()

        first_reading = d[0]
        if "date_obs" not in first_reading or "resultat_obs" not in first_reading:
            _LOGGER.warning(first_reading)
            raise Exception("unexpected format of first_reading")

        reading = {"date_obs": first_reading["date_obs"],
                   "resultat_obs": first_reading["resultat_obs"]}
        return reading
