# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class SmartLoggerStation(models.Model):
    _name = 'smartlogger.station'
    _description = 'Станція SmartLogger'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char('Назва станції', required=True, tracking=True)
    station_code = fields.Char('Код станції', required=True, unique=True, tracking=True,
                               help="Унікальний код станції з FusionSolar.")
    capacity = fields.Float('Потужність (кВт)', help="Номінальна потужність станції.")
    current_power = fields.Float('Поточна потужність (кВт)', tracking=True,
                                 help="Поточна вироблена потужність станції.")
    daily_energy = fields.Float('Добова енергія (кВт·год)', tracking=True,
                                help="Загальна вироблена енергія за поточний день.")
    monthly_energy = fields.Float('Місячна енергія (кВт·год)', tracking=True,
                                  help="Загальна вироблена енергія за поточний місяць.")
    yearly_energy = fields.Float('Річна енергія (кВт·год)', tracking=True,
                                 help="Загальна вироблена енергія за поточний рік.")
    lifetime_energy = fields.Float('Загальна енергія (кВт·год)', tracking=True,
                                   help="Загальна вироблена енергія за весь час роботи станції.")
    last_sync = fields.Datetime('Остання синхронізація', readonly=True, tracking=True)

    # Поле для зберігання історичних даних
    kpi_data_ids = fields.One2many('smartlogger.data', 'station_id', string='Історичні дані KPI')

    _sql_constraints = [
        ('station_code_unique', 'unique(station_code)', 'Код станції повинен бути унікальним!'),
    ]

    @api.model
    def _get_fusionsolar_api_credentials(self):
        """Отримує облікові дані FusionSolar API з системних параметрів."""
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        base_url = IrConfigParameter.get_param('huawei.fusionsolar.base_url', 'https://eu5.fusionsolar.huawei.com/thirdData')
        username = IrConfigParameter.get_param('huawei.fusionsolar.username')
        password = IrConfigParameter.get_param('huawei.fusionsolar.password')

        if not username or not password:
            _logger.error("FusionSolar API: Облікові дані (username/password) не налаштовані в системних параметрах.")
            raise UserError(_("Будь ласка, налаштуйте ім'я користувача та пароль FusionSolar API у Налаштуваннях > Системні параметри."))
        return base_url, username, password

    @api.model
    def sync_fusionsolar_data(self):
        """
        Синхронізує дані всіх станцій з FusionSolar API.
        Цей метод викликається Cron-завданням.
        """
        _logger.info("Початок синхронізації даних FusionSolar.")
        base_url, username, password = self._get_fusionsolar_api_credentials()
        session = requests.Session()
        token = None

        try:
            # Аутентифікація
            login_url = f"{base_url}/login"
            login_data = {
                "userName": username,
                "systemCode": password
            }
            response = session.post(login_url, json=login_data, timeout=30)

            response.raise_for_status()
            token = response.headers.get('xsrf-token')
            if not token:
                raise UserError(_("Не вдалося отримати токен XSRF після входу."))

            _logger.info("FusionSolar API: Успішна аутентифікація.")

            # Отримання списку станцій
            stations_url = f"{base_url}/getStationList"
            headers = {'XSRF-TOKEN': token, 'Content-Type': 'application/json'}
            stations_response = session.post(stations_url, headers=headers, timeout=30)

            stations_response.raise_for_status()
            stations_data = stations_response.json()

            if stations_data.get('success'):
                for station_info in stations_data.get('data', []):
                    self._update_station_data(station_info, token, session, base_url)
                _logger.info("Синхронізація даних FusionSolar завершена успішно.")
            else:
                _logger.error("FusionSolar API: Не вдалося отримати список станцій. Помилка: %s", stations_data.get('failCode'))
                raise UserError(_("Не вдалося отримати список станцій з FusionSolar API. Помилка: %s") % stations_data.get('failCode'))

        except requests.exceptions.RequestException as e:
            _logger.error("Помилка мережі або API під час синхронізації FusionSolar: %s", str(e))
            raise UserError(_("Помилка мережі або API під час синхронізації FusionSolar: %s") % str(e))
        except json.JSONDecodeError:
            _logger.error("Помилка декодування JSON відповіді від FusionSolar API.")
            raise UserError(_("Недійсна JSON відповідь від FusionSolar API."))
        except Exception as e:
            _logger.error("Неочікувана помилка під час синхронізації FusionSolar: %s", str(e))
            raise UserError(_("Неочікувана помилка під час синхронізації FusionSolar: %s") % str(e))
        finally:
            if session:
                session.close()

    def _update_station_data(self, station_data, token, session, base_url):
        """
        Оновлює або створює запис станції та отримує її дані KPI.
        """
        station_code = station_data.get('stationCode')
        if not station_code:
            _logger.warning("Пропущено станцію без коду станції: %s", station_data)
            return

        station = self.search([('station_code', '=', station_code)], limit=1)
        if not station:
            _logger.info("Створення нової станції: %s (%s)", station_data.get('stationName'), station_code)
            station = self.create({
                'name': station_data.get('stationName', _("Невідома станція")),
                'station_code': station_code,
                'capacity': station_data.get('capacity', 0.0)
            })
        else:
            _logger.info("Оновлення існуючої станції: %s", station.name)

        # Отримання даних KPI в реальному часі
        realtime_url = f"{base_url}/getStationRealKpi"
        headers = {'XSRF-TOKEN': token, 'Content-Type': 'application/json'}
        realtime_data = {"stationCodes": station_code}

        try:
            realtime_response = session.post(realtime_url, json=realtime_data, headers=headers, timeout=30)
            realtime_response.raise_for_status()
            kpi_response_json = realtime_response.json()

            if kpi_response_json.get('success'):
                kpi_list = kpi_response_json.get('data', [])
                if kpi_list:
                    station_kpi = kpi_list[0].get('dataItemMap', {})

                    # Оновлення полів станції
                    station.write({
                        'current_power': station_kpi.get('real_power', 0.0),
                        'daily_energy': station_kpi.get('day_power', 0.0),
                        'monthly_energy': station_kpi.get('month_power', 0.0),
                        'yearly_energy': station_kpi.get('year_power', 0.0),
                        'lifetime_energy': station_kpi.get('total_power', 0.0),
                        'last_sync': fields.Datetime.now()
                    })
                    _logger.info("Дані KPI для станції %s оновлено.", station.name)

                    # Зберігаємо історичні дані KPI
                    self.env['smartlogger.data'].create({
                        'station_id': station.id,
                        'timestamp': fields.Datetime.now(),
                        'current_power': station_kpi.get('real_power', 0.0),
                        'daily_energy': station_kpi.get('day_power', 0.0),
                        'monthly_energy': station_kpi.get('month_power', 0.0),
                        'yearly_energy': station_kpi.get('year_power', 0.0),
                        'lifetime_energy': station_kpi.get('total_power', 0.0),
                    })
                else:
                    _logger.warning("Немає даних KPI для станції %s (%s).", station.name, station_code)
            else:
                _logger.error("FusionSolar API: Не вдалося отримати KPI для станції %s. Помилка: %s", station_code, kpi_response_json.get('failCode'))

        except requests.exceptions.RequestException as e:
            _logger.error("Помилка мережі або API під час отримання KPI для станції %s: %s", station_code, str(e))
        except json.JSONDecodeError:
            _logger.error("Помилка декодування JSON відповіді для KPI станції %s.", station_code)
        except Exception as e:
            _logger.error("Неочікувана помилка під час оновлення даних станції %s: %s", station_code, str(e))

    def action_sync_data(self):
        """
        Дія для ручної синхронізації даних через інтерфейс.
        """
        try:
            self.sync_fusionsolar_data()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': _('Синхронізація завершена успішно!'),
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'danger',
                    'message': _('Помилка синхронізації: %s') % str(e),
                    'sticky': True,
                }
            }