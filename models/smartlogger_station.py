# -*- coding: utf-8 -*-
# ФАЙЛ: models/smartlogger_station.py
# ЗАМЕНИТЬ ПОЛНОСТЬЮ существующий файл

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import json
import logging
from datetime import datetime, timedelta
import time

_logger = logging.getLogger(__name__)


class SmartLoggerStation(models.Model):
    _name = 'smartlogger.station'
    _description = 'Станція SmartLogger'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char('Назва станції', required=True, tracking=True)
    station_code = fields.Char('Код станції', required=True, tracking=True,
                               help="Унікальний код станції з FusionSolar.")
    plant_code = fields.Char('Код електростанції', tracking=True,
                             help="Код електростанції (plantCode) - альтернативний ідентифікатор.")
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

    # Додаткові поля для множественних станцій
    region = fields.Char('Регіон', help="Регіон розташування станції")
    api_endpoint = fields.Char('API Endpoint', help="Специфічний endpoint для цієї станції")
    sync_priority = fields.Integer('Пріоритет синхронізації', default=10,
                                   help="Пріоритет синхронізації (1-найвищий, 10-найнижчий)")
    batch_group = fields.Char('Група пакетної обробки', default='default',
                              help="Група для пакетної обробки станцій")

    # Поле статусу
    status = fields.Selection([
        ('active', 'Активна'),
        ('inactive', 'Неактивна'),
        ('maintenance', 'Обслуговування'),
        ('error', 'Помилка'),
        ('sync_error', 'Помилка синхронізації'),
    ], string='Статус', default='active', tracking=True)

    # Статистика синхронізації
    sync_attempts = fields.Integer('Спроби синхронізації', default=0, readonly=True)
    last_error = fields.Text('Остання помилка', readonly=True)
    successful_syncs = fields.Integer('Успішні синхронізації', default=0, readonly=True)

    # Поле для зберігання історичних даних
    kpi_data_ids = fields.One2many('smartlogger.data', 'station_id', string='Історичні дані KPI')

    _sql_constraints = [
        ('station_code_unique', 'unique(station_code)', 'Код станції повинен бути унікальним!'),
    ]

    @api.model
    def _get_fusionsolar_api_credentials(self):
        """Отримує облікові дані FusionSolar API з системних параметрів."""
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        base_url = IrConfigParameter.get_param('huawei.fusionsolar.base_url',
                                               'https://eu5.fusionsolar.huawei.com/thirdData')
        username = IrConfigParameter.get_param('huawei.fusionsolar.username')
        password = IrConfigParameter.get_param('huawei.fusionsolar.password')
        batch_size = int(IrConfigParameter.get_param('huawei.fusionsolar.batch_size', '20'))
        request_delay = float(IrConfigParameter.get_param('huawei.fusionsolar.request_delay', '1.0'))

        if not username or not password:
            _logger.error("FusionSolar API: Облікові дані (username/password) не налаштовані в системних параметрах.")
            raise UserError(
                _("Будь ласка, налаштуйте ім'я користувача та пароль FusionSolar API у Налаштуваннях > Системні параметри."))

        return base_url, username, password, batch_size, request_delay

    @api.model
    def _check_api_blocked_status(self):
        """Перевіряє, чи заблокований API через неправильні облікові дані."""
        IrConfigParameter = self.env['ir.config_parameter'].sudo()

        # Перевіряємо статус блокировки
        api_blocked = IrConfigParameter.get_param('huawei.fusionsolar.api_blocked', 'false') == 'true'
        last_auth_error = IrConfigParameter.get_param('huawei.fusionsolar.last_auth_error')
        auth_error_count = int(IrConfigParameter.get_param('huawei.fusionsolar.auth_error_count', '0'))

        if api_blocked:
            block_reason = IrConfigParameter.get_param('huawei.fusionsolar.block_reason', 'Неправильні облікові дані')
            _logger.warning("FusionSolar API заблокований: %s", block_reason)
            raise UserError(_(
                "FusionSolar API тимчасово заблокований через помилки автентифікації.\n\n"
                "Причина: %s\n"
                "Кількість помилок: %d\n"
                "Остання помилка: %s\n\n"
                "Перевірте облікові дані та натисніть 'Скинути блокування API' для відновлення роботи."
            ) % (block_reason, auth_error_count, last_auth_error or 'Невідомо'))

        return True

    @api.model
    def _handle_auth_error(self, error_message):
        """Обробляє помилки автентифікації та блокує API при необхідності."""
        IrConfigParameter = self.env['ir.config_parameter'].sudo()

        # Збільшуємо лічильник помилок
        auth_error_count = int(IrConfigParameter.get_param('huawei.fusionsolar.auth_error_count', '0'))
        auth_error_count += 1

        # Записуємо дані про помилку
        IrConfigParameter.set_param('huawei.fusionsolar.auth_error_count', str(auth_error_count))
        IrConfigParameter.set_param('huawei.fusionsolar.last_auth_error', error_message)
        IrConfigParameter.set_param('huawei.fusionsolar.last_auth_error_time', fields.Datetime.now())

        _logger.error("FusionSolar API помилка автентифікації #%d: %s", auth_error_count, error_message)

        # Блокуємо API після 3 неуспішних спроб
        max_auth_errors = int(IrConfigParameter.get_param('huawei.fusionsolar.max_auth_errors', '3'))
        if auth_error_count >= max_auth_errors:
            IrConfigParameter.set_param('huawei.fusionsolar.api_blocked', 'true')
            IrConfigParameter.set_param('huawei.fusionsolar.block_reason',
                                        'Перевищено максимальну кількість помилок автентифікації (%d)' % max_auth_errors)
            IrConfigParameter.set_param('huawei.fusionsolar.block_time', fields.Datetime.now())

            _logger.critical("FusionSolar API ЗАБЛОКОВАНИЙ після %d помилок автентифікації", auth_error_count)

            # Вимикаємо автоматичні cron завдання
            cron_jobs = self.env['ir.cron'].search([('name', 'ilike', 'SmartLogger')])
            cron_jobs.write({'active': False})
            _logger.warning("Вимкнено %d автоматичних завдань SmartLogger", len(cron_jobs))

    @api.model
    def reset_api_block(self):
        """Скидає блокування API та скидає лічильники помилок."""
        IrConfigParameter = self.env['ir.config_parameter'].sudo()

        # Скидаємо всі параметри блокировки
        IrConfigParameter.set_param('huawei.fusionsolar.api_blocked', 'false')
        IrConfigParameter.set_param('huawei.fusionsolar.auth_error_count', '0')
        IrConfigParameter.set_param('huawei.fusionsolar.last_auth_error', '')
        IrConfigParameter.set_param('huawei.fusionsolar.block_reason', '')
        IrConfigParameter.set_param('huawei.fusionsolar.reset_time', fields.Datetime.now())

        # Включаємо назад автоматичні cron завдання
        cron_jobs = self.env['ir.cron'].search([('name', 'ilike', 'SmartLogger')])
        cron_jobs.write({'active': True})

        _logger.info("FusionSolar API блокування скинуто. Увімкнено %d автоматичних завдань", len(cron_jobs))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Блокування API скинуто успішно! Автоматичні завдання відновлено.'),
                'sticky': False,
            }
        }

    @api.model
    def sync_fusionsolar_data(self):
        """
        Синхронізує дані всіх станцій з FusionSolar API з оптимізацією для множественних станцій.
        """
        _logger.info("Початок синхронізації даних FusionSolar.")

        try:
            # Перевіряємо, чи не заблокований API
            self._check_api_blocked_status()

            base_url, username, password, batch_size, request_delay = self._get_fusionsolar_api_credentials()

            # Отримуємо або оновлюємо список станцій
            self._update_station_list(base_url, username, password, request_delay)

            # Синхронізуємо дані станцій пакетами
            self._sync_stations_batch(base_url, username, password, batch_size, request_delay)

            # Якщо дійшли до цього місця, значить синхронізація пройшла успішно
            # Скидаємо лічильник помилок автентифікації
            IrConfigParameter = self.env['ir.config_parameter'].sudo()
            IrConfigParameter.set_param('huawei.fusionsolar.auth_error_count', '0')
            IrConfigParameter.set_param('huawei.fusionsolar.last_successful_sync', fields.Datetime.now())

            _logger.info("Синхронізація даних FusionSolar завершена успішно.")

            return {
                'success': True,
                'message': _("Синхронізація завершена успішно"),
                'stations_processed': len(self.search([]))
            }

        except UserError as ue:
            # UserError уже содержит сообщение о блокировке API или другие проблемы
            _logger.error("UserError під час синхронізації: %s", str(ue))
            raise
        except Exception as e:
            error_msg = str(e)
            _logger.error("Помилка під час синхронізації FusionSolar: %s", error_msg)

            # Перевіряємо, чи це помилка автентифікації за ключовими словами
            auth_keywords = [
                '401', 'unauthorized', 'authentication', 'login', 'token', 'credential',
                'user.login.user_or_value_invalid', 'failCode": 20400', 'failCode: 20400',
                'неправильні облікові дані', 'доступ заборонено', 'права користувача'
            ]

            if any(auth_keyword in error_msg.lower() for auth_keyword in auth_keywords):
                self._handle_auth_error(error_msg)

            raise

    def _update_station_list(self, base_url, username, password, request_delay):
        """Оновлює список станцій з API з підтримкою пагинації."""
        session = requests.Session()
        token = None

        try:
            # Аутентифікація
            token = self._authenticate(session, base_url, username, password)

            # Отримання списку станцій з пагинацією
            all_stations = []
            page_no = 1
            page_size = 100  # Максимальний розмір сторінки

            while True:
                _logger.info(f"Завантаження сторінки {page_no} списку станцій...")

                # Спробуємо новий метод /stations
                stations_data = self._fetch_stations_page(
                    session, base_url, token, page_no, page_size
                )

                if not stations_data or not stations_data.get('data'):
                    # Якщо новий метод не працює, спробуємо старий getStationList
                    _logger.warning("Метод /stations не працює, спробуємо getStationList...")
                    stations_data = self._fetch_stations_legacy(session, base_url, token)

                    if stations_data and stations_data.get('data'):
                        all_stations.extend(stations_data['data'])
                    break

                stations_page = stations_data.get('data', [])
                if not stations_page:
                    break

                all_stations.extend(stations_page)

                # Перевіряємо, чи є ще сторінки
                total_count = stations_data.get('total', 0)
                if len(all_stations) >= total_count or len(stations_page) < page_size:
                    break

                page_no += 1
                time.sleep(request_delay)  # Затримка між запитами

            _logger.info(f"Знайдено {len(all_stations)} станцій у API")

            # Створюємо або оновлюємо записи станцій
            for station_data in all_stations:
                self._create_or_update_station(station_data)

        except Exception as e:
            _logger.error("Помилка при оновленні списку станцій: %s", str(e))
            raise
        finally:
            if session:
                session.close()

    def _fetch_stations_page(self, session, base_url, token, page_no, page_size):
        """Отримує сторінку станцій через новий API /stations."""
        try:
            stations_url = f"{base_url}/stations"
            headers = {'XSRF-TOKEN': token, 'Content-Type': 'application/json'}
            payload = {
                "pageNo": str(page_no),
                "pageSize": str(page_size)
            }

            response = session.post(stations_url, json=payload, headers=headers, timeout=30)

            if response.status_code != 200:
                _logger.warning("API /stations повернув HTTP %d", response.status_code)
                return None

            try:
                data = response.json()
            except json.JSONDecodeError:
                _logger.warning("Неправильна JSON відповідь від API /stations")
                return None

            if data.get('success'):
                return data
            else:
                fail_code = data.get('failCode')
                message = data.get('message', '')
                _logger.error("Помилка API /stations: failCode=%s, message=%s", fail_code, message)
                return None

        except Exception as e:
            _logger.warning("Не вдалося використати новий API /stations: %s", str(e))
            return None

    def _fetch_stations_legacy(self, session, base_url, token):
        """Отримує станції через застарілий API getStationList."""
        try:
            stations_url = f"{base_url}/getStationList"
            headers = {'XSRF-TOKEN': token, 'Content-Type': 'application/json'}

            response = session.post(stations_url, headers=headers, timeout=30)

            if response.status_code != 200:
                _logger.error("API getStationList повернув HTTP %d", response.status_code)
                return None

            try:
                data = response.json()
            except json.JSONDecodeError:
                _logger.error("Неправильна JSON відповідь від API getStationList")
                return None

            if data.get('success'):
                return data
            else:
                fail_code = data.get('failCode')
                message = data.get('message', '')
                _logger.error("Помилка API getStationList: failCode=%s, message=%s", fail_code, message)
                return None

        except Exception as e:
            _logger.error("Не вдалося використати застарілий API getStationList: %s", str(e))
            return None

    def _create_or_update_station(self, station_data):
        """Створює або оновлює запис станції."""
        station_code = station_data.get('stationCode') or station_data.get('plantCode')
        plant_code = station_data.get('plantCode') or station_data.get('stationCode')

        if not station_code:
            _logger.warning("Пропущено станцію без коду: %s", station_data)
            return

        station = self.search([('station_code', '=', station_code)], limit=1)

        values = {
            'name': station_data.get('stationName') or station_data.get('plantName', _("Невідома станція")),
            'station_code': station_code,
            'plant_code': plant_code,
            'capacity': station_data.get('capacity', 0.0),
            'status': 'active'
        }

        if not station:
            _logger.info("Створення нової станції: %s (%s)", values['name'], station_code)
            station = self.create(values)
        else:
            _logger.info("Оновлення існуючої станції: %s", station.name)
            # Оновлюємо тільки основні поля, не торкаючись статистики
            update_values = {k: v for k, v in values.items() if k not in ['status']}
            station.write(update_values)

    def _sync_stations_batch(self, base_url, username, password, batch_size, request_delay):
        """Синхронізує дані станцій пакетами для оптимізації API запитів."""
        session = requests.Session()
        token = None

        try:
            # Аутентифікація
            token = self._authenticate(session, base_url, username, password)

            # Отримуємо всі станції, сортовані за пріоритетом
            stations = self.search([], order='sync_priority ASC, id ASC')

            _logger.info(f"Початок синхронізації {len(stations)} станцій пакетами по {batch_size}")

            # Групуємо станції за batch_group
            groups = {}
            for station in stations:
                group = station.batch_group or 'default'
                if group not in groups:
                    groups[group] = []
                groups[group].append(station)

            # Обробляємо кожну групу
            for group_name, group_stations in groups.items():
                _logger.info(f"Обробка групи '{group_name}' ({len(group_stations)} станцій)")

                # Розбиваємо групу на пакети
                for i in range(0, len(group_stations), batch_size):
                    batch = group_stations[i:i + batch_size]
                    self._process_stations_batch(session, base_url, token, batch, request_delay)

                    # Затримка між пакетами для уникнення перевантаження API
                    if i + batch_size < len(group_stations):
                        time.sleep(request_delay * 2)

        except Exception as e:
            _logger.error("Помилка при пакетній синхронізації: %s", str(e))
            raise
        finally:
            if session:
                session.close()

    def _process_stations_batch(self, session, base_url, token, stations, request_delay):
        """Обробляє пакет станцій за один API запит."""
        if not stations:
            return

        # Формуємо список кодів станцій для пакетного запиту
        station_codes = []
        station_map = {}

        for station in stations:
            code = station.station_code
            station_codes.append(code)
            station_map[code] = station

            # Оновлюємо статистику спроб
            station.sync_attempts += 1

        _logger.info(
            f"Обробка пакету з {len(station_codes)} станцій: {', '.join(station_codes[:3])}{'...' if len(station_codes) > 3 else ''}")

        try:
            # Пакетний запит KPI
            kpi_data = self._fetch_batch_kpi(session, base_url, token, station_codes)

            if kpi_data and kpi_data.get('success'):
                # Обробляємо результати для кожної станції
                for kpi_item in kpi_data.get('data', []):
                    station_code = kpi_item.get('stationCode')
                    if station_code in station_map:
                        self._update_station_kpi(station_map[station_code], kpi_item)
            else:
                # Якщо пакетний запит не вдався, обробляємо кожну станцію окремо
                _logger.warning("Пакетний запит не вдався, обробляємо станції окремо")
                for station in stations:
                    self._process_single_station(session, base_url, token, station)
                    time.sleep(request_delay)

        except Exception as e:
            _logger.error(f"Помилка обробки пакету станцій: {str(e)}")
            # При помилці обробляємо кожну станцію окремо
            for station in stations:
                try:
                    self._process_single_station(session, base_url, token, station)
                    time.sleep(request_delay)
                except Exception as single_error:
                    _logger.error(f"Помилка обробки станції {station.station_code}: {str(single_error)}")
                    station.write({
                        'status': 'sync_error',
                        'last_error': str(single_error)
                    })

    def _fetch_batch_kpi(self, session, base_url, token, station_codes):
        """Отримує KPI для пакету станцій за один запит."""
        try:
            kpi_url = f"{base_url}/getStationRealKpi"
            headers = {'XSRF-TOKEN': token, 'Content-Type': 'application/json'}

            # Формуємо запит з масивом кодів станцій
            payload = {
                "stationCodes": ",".join(station_codes)  # Коми-розділений список
            }

            response = session.post(kpi_url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            _logger.error(f"Помилка пакетного запиту KPI: {str(e)}")
            return None

    def _process_single_station(self, session, base_url, token, station):
        """Обробляє окрему станцію."""
        try:
            kpi_data = self._fetch_station_kpi(session, base_url, token, station.station_code)

            if kpi_data and kpi_data.get('success'):
                kpi_list = kpi_data.get('data', [])
                if kpi_list:
                    self._update_station_kpi(station, kpi_list[0])
                else:
                    station.write({'status': 'inactive'})
            else:
                station.write({
                    'status': 'sync_error',
                    'last_error': f"API помилка: {kpi_data.get('failCode') if kpi_data else 'Немає відповіді'}"
                })

        except Exception as e:
            _logger.error(f"Помилка обробки станції {station.station_code}: {str(e)}")
            station.write({
                'status': 'sync_error',
                'last_error': str(e)
            })

    def _fetch_station_kpi(self, session, base_url, token, station_code):
        """Отримує KPI для окремої станції."""
        try:
            kpi_url = f"{base_url}/getStationRealKpi"
            headers = {'XSRF-TOKEN': token, 'Content-Type': 'application/json'}
            payload = {"stationCodes": station_code}

            response = session.post(kpi_url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            _logger.error(f"Помилка запиту KPI для станції {station_code}: {str(e)}")
            return None

    def _update_station_kpi(self, station, kpi_data):
        """Оновлює KPI данні станції."""
        try:
            station_kpi = kpi_data.get('dataItemMap', {})

            # Визначаємо статус на основі даних
            current_power = station_kpi.get('real_power', 0.0)
            new_status = 'active' if current_power > 0 else 'inactive'

            # Оновлення полів станції
            station.write({
                'current_power': current_power,
                'daily_energy': station_kpi.get('day_power', 0.0),
                'monthly_energy': station_kpi.get('month_power', 0.0),
                'yearly_energy': station_kpi.get('year_power', 0.0),
                'lifetime_energy': station_kpi.get('total_power', 0.0),
                'last_sync': fields.Datetime.now(),
                'status': new_status,
                'successful_syncs': station.successful_syncs + 1,
                'last_error': False
            })

            # Зберігаємо історичні дані KPI
            self.env['smartlogger.data'].create({
                'station_id': station.id,
                'timestamp': fields.Datetime.now(),
                'current_power': current_power,
                'daily_energy': station_kpi.get('day_power', 0.0),
                'monthly_energy': station_kpi.get('month_power', 0.0),
                'yearly_energy': station_kpi.get('year_power', 0.0),
                'lifetime_energy': station_kpi.get('total_power', 0.0),
            })

            _logger.info(f"KPI станції {station.name} оновлено. Потужність: {current_power} кВт")

        except Exception as e:
            _logger.error(f"Помилка оновлення KPI станції {station.station_code}: {str(e)}")
            station.write({
                'status': 'error',
                'last_error': str(e)
            })

    def _authenticate(self, session, base_url, username, password):
        """Аутентифікація в API з правильною обробкою JSON відповідей."""
        try:
            login_url = f"{base_url}/login"
            login_data = {
                "userName": username,
                "systemCode": password
            }

            response = session.post(login_url, json=login_data, timeout=30)

            # Перевіряємо HTTP статус
            if response.status_code != 200:
                error_msg = _("Помилка HTTP %d при підключенні до API") % response.status_code
                self._handle_auth_error(error_msg)
                raise UserError(error_msg)

            # Парсимо JSON відповідь
            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                error_msg = _("Неправильна JSON відповідь від API: %s") % str(e)
                self._handle_auth_error(error_msg)
                raise UserError(error_msg)

            # Перевіряємо успішність операції в JSON
            if not response_data.get('success', False):
                fail_code = response_data.get('failCode')
                api_message = response_data.get('message', '')

                # Визначаємо тип помилки за кодом
                if fail_code == 20400:
                    error_msg = _("Неправильні облікові дані API (логін або пароль). Перевірте username та password.")
                elif fail_code in [20401, 20403]:
                    error_msg = _("Доступ заборонено. Перевірте права користувача API або термін дії облікових даних.")
                elif fail_code == 20404:
                    error_msg = _("API endpoint не знайдено. Перевірте URL сервера.")
                elif fail_code == 20429:
                    error_msg = _("Перевищено ліміт запитів API. Спробуйте пізніше.")
                elif fail_code == 20500:
                    error_msg = _("Внутрішня помилка сервера Huawei. Спробуйте пізніше.")
                else:
                    error_msg = _("Помилка API: код %s, повідомлення: %s") % (fail_code, api_message)

                # Логуємо детальну інформацію
                _logger.error(
                    "FusionSolar API автентифікація відхилена: failCode=%s, message=%s, response=%s",
                    fail_code, api_message, response_data
                )

                self._handle_auth_error(error_msg)
                raise UserError(error_msg)

            # Отримуємо токен з заголовків
            token = response.headers.get('xsrf-token') or response.headers.get('XSRF-TOKEN')
            if not token:
                error_msg = _("Не вдалося отримати токен XSRF з відповіді API. Можливо, проблема з сервером.")
                self._handle_auth_error(error_msg)
                raise UserError(error_msg)

            _logger.info("FusionSolar API: Успішна аутентифікація. Токен отримано.")
            return token

        except requests.exceptions.Timeout:
            error_msg = _("Таймаут підключення до API. Перевірте мережеве з'єднання.")
            _logger.error("Таймаут автентифікації: %s", error_msg)
            raise UserError(error_msg)
        except requests.exceptions.ConnectionError:
            error_msg = _("Помилка з'єднання з API. Перевірте URL сервера та мережеве з'єднання.")
            _logger.error("Помилка з'єднання автентифікації: %s", error_msg)
            raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = _("Помилка мережі при автентифікації: %s") % str(e)
            _logger.error("Помилка мережі автентифікації: %s", str(e))
            raise UserError(error_msg)
        except UserError:
            # UserError уже оброблені вище
            raise
        except Exception as e:
            error_msg = _("Неочікувана помилка автентифікації: %s") % str(e)
            _logger.error("Неочікувана помилка автентифікації: %s", str(e), exc_info=True)
            self._handle_auth_error(error_msg)
            raise UserError(error_msg)

    def action_sync_data(self):
        """Дія для ручної синхронізації даних через інтерфейс."""
        try:
            result = self.sync_fusionsolar_data()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': result.get('message', _('Синхронізація завершена успішно!')),
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

    @api.model
    def cleanup_old_kpi_data(self, days_to_keep=90):
        """Очищення старих KPI даних для економії місця."""
        cutoff_date = fields.Datetime.now() - timedelta(days=days_to_keep)
        old_records = self.env['smartlogger.data'].search([
            ('timestamp', '<', cutoff_date)
        ])

        count = len(old_records)
        old_records.unlink()
        _logger.info(f"Видалено {count} старих записів KPI (старіше {days_to_keep} днів)")

        return count

    @api.model
    def cleanup_old_kpi_data(self, days_to_keep=90):
        """Очищення старих KPI даних для економії місця."""
        cutoff_date = fields.Datetime.now() - timedelta(days=days_to_keep)
        old_records = self.env['smartlogger.data'].search([
            ('timestamp', '<', cutoff_date)
        ])

        count = len(old_records)
        old_records.unlink()
        _logger.info(f"Видалено {count} старих записів KPI (старіше {days_to_keep} днів)")

        return count

    @api.model
    def _monitor_station_health(self):
        """Моніторинг стану станцій та логування статистики."""
        try:
            stations = self.search([])
            current_time = datetime.now()

            # Статистика по статусах
            status_stats = {}
            sync_stats = {
                'never_synced': 0,
                'outdated': 0,
                'recent': 0,
                'errors': 0
            }

            for station in stations:
                # Статистика статусів
                status = station.status
                if status not in status_stats:
                    status_stats[status] = 0
                status_stats[status] += 1

                # Статистика синхронізації
                if not station.last_sync:
                    sync_stats['never_synced'] += 1
                else:
                    time_diff = current_time - station.last_sync
                    if time_diff.total_seconds() > 7200:  # 2 години
                        sync_stats['outdated'] += 1
                    else:
                        sync_stats['recent'] += 1

                # Статистика помилок
                if station.status in ['error', 'sync_error']:
                    sync_stats['errors'] += 1

            # Логування статистики
            _logger.info(
                "Моніторинг стану станцій: Всього=%d, Активних=%d, Помилок=%d, Не синхронізованих=%d, Застарілих=%d",
                len(stations),
                status_stats.get('active', 0),
                sync_stats['errors'],
                sync_stats['never_synced'],
                sync_stats['outdated']
            )

            # Перевіряємо критичні проблеми
            if sync_stats['errors'] > len(stations) * 0.1:  # Більше 10% станцій з помилками
                _logger.warning("Критично: Більше 10%% станцій (%d з %d) мають помилки синхронізації",
                                sync_stats['errors'], len(stations))

            if sync_stats['never_synced'] > 0:
                _logger.warning("Увага: %d станцій ніколи не синхронізувались", sync_stats['never_synced'])

            return {
                'success': True,
                'total_stations': len(stations),
                'status_stats': status_stats,
                'sync_stats': sync_stats
            }

        except Exception as e:
            _logger.error("Помилка моніторингу станцій: %s", str(e))
            return {
                'success': False,
                'error': str(e)
            }