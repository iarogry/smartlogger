# -*- coding: utf-8 -*-
# ФАЙЛ: wizards/sync_data_wizard.py
# ЗАМЕНИТЬ ПОЛНОСТЬЮ существующий файл

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class SyncDataWizard(models.TransientModel):
    _name = 'smartlogger.sync.data.wizard'
    _description = 'Майстер синхронізації даних SmartLogger'

    # Основні поля статусу
    message = fields.Char(string='Статус', readonly=True)
    sync_status = fields.Selection([
        ('waiting', 'Очікування'),
        ('running', 'Виконується'),
        ('success', 'Успішно'),
        ('error', 'Помилка'),
        ('partial_success', 'Частково успішно')
    ], string='Статус синхронізації', default='waiting', readonly=True)

    last_sync_date = fields.Datetime(string='Остання синхронізація', readonly=True)
    sync_details = fields.Text(string='Деталі синхронізації', readonly=True)

    # Розширені поля для статистики
    total_stations = fields.Integer('Загальна кількість станцій', readonly=True, default=0)
    stations_found = fields.Integer('Станцій знайдено в API', readonly=True, default=0)
    stations_updated = fields.Integer('Станцій оновлено', readonly=True, default=0)
    stations_created = fields.Integer('Станцій створено', readonly=True, default=0)
    stations_errors = fields.Integer('Станцій з помилками', readonly=True, default=0)

    # Опції синхронізації
    sync_mode = fields.Selection([
        ('full', 'Повна синхронізація'),
        ('incremental', 'Інкрементальна синхронізація'),
        ('stations_only', 'Тільки список станцій'),
        ('data_only', 'Тільки дані KPI')
    ], string='Режим синхронізації', default='full')

    force_refresh = fields.Boolean('Примусове оновлення', default=False,
                                   help="Оновити всі станції, навіть якщо синхронізація була недавно")

    batch_processing = fields.Boolean('Пакетна обробка', default=True,
                                      help="Використовувати пакетну обробку для кращої продуктивності")

    selected_station_ids = fields.Many2many('smartlogger.station', string='Вибрані станції',
                                            help="Залишіть порожнім для синхронізації всіх станцій")

    # Результати синхронізації
    sync_results = fields.Text('Результати синхронізації', readonly=True)
    error_details = fields.Text('Деталі помилок', readonly=True)
    performance_stats = fields.Text('Статистика продуктивності', readonly=True)

    @api.model
    def default_get(self, fields_list):
        """Встановлює значення за замовчуванням при відкритті майстра."""
        res = super(SyncDataWizard, self).default_get(fields_list)

        try:
            # Отримуємо статистику існуючих станцій
            stations = self.env['smartlogger.station'].search([])
            res['total_stations'] = len(stations)

            if stations:
                # Знаходимо останню синхронізацію
                last_synced_station = stations.filtered('last_sync').sorted('last_sync', reverse=True)
                if last_synced_station:
                    res['last_sync_date'] = last_synced_station[0].last_sync

                # Статистика по статусах
                active_count = len(stations.filtered(lambda s: s.status == 'active'))
                error_count = len(stations.filtered(lambda s: s.status in ['error', 'sync_error']))

                res['message'] = _(
                    "Готовий до синхронізації. Станцій: %d (активних: %d, з помилками: %d)"
                ) % (len(stations), active_count, error_count)
            else:
                res['message'] = _("Станції не знайдено. Запустіть синхронізацію для імпорту станцій з API.")

            # Перевіряємо налаштування
            self._check_api_configuration(res)

        except Exception as e:
            _logger.warning("Помилка при отриманні статистики: %s", e)
            res['message'] = _("Готовий до синхронізації")

        return res

    def _check_api_configuration(self, res):
        """Перевіряє налаштування API."""
        try:
            IrConfigParameter = self.env['ir.config_parameter'].sudo()
            username = IrConfigParameter.get_param('huawei.fusionsolar.username')
            password = IrConfigParameter.get_param('huawei.fusionsolar.password')

            if not username or not password:
                res['sync_status'] = 'error'
                res['message'] = _(
                    "Помилка: Не налаштовані облікові дані API. Перейдіть до Конфігурація > Налаштування API.")
                res['error_details'] = _("Відсутні обов'язкові параметри username та/або password")

        except Exception as e:
            _logger.error("Помилка перевірки конфігурації: %s", e)

    def action_sync_now(self):
        """Запускає синхронізацію даних FusionSolar з розширеною логікою."""
        self.sync_status = 'running'
        self.message = _("Синхронізація розпочата...")

        start_time = datetime.now()
        sync_results = {
            'stations_processed': 0,
            'stations_created': 0,
            'stations_updated': 0,
            'stations_errors': 0,
            'api_calls_made': 0,
            'errors': []
        }

        try:
            # Перевіряємо налаштування
            if not self._validate_configuration():
                return self._return_error_result(_("Неправильні налаштування API"))

            _logger.info("Запуск синхронізації SmartLogger. Режим: %s", self.sync_mode)

            # Виконуємо синхронізацію залежно від режиму
            if self.sync_mode == 'full':
                result = self._perform_full_sync()
            elif self.sync_mode == 'incremental':
                result = self._perform_incremental_sync()
            elif self.sync_mode == 'stations_only':
                result = self._perform_stations_only_sync()
            elif self.sync_mode == 'data_only':
                result = self._perform_data_only_sync()
            else:
                result = self._perform_full_sync()

            # Обробляємо результати
            self._process_sync_results(result, start_time)

        except UserError as e:
            return self._handle_sync_error(str(e), start_time)
        except Exception as e:
            return self._handle_sync_error(str(e), start_time, unexpected=True)

        return self._return_updated_form()

    def action_reset_api_block(self):
        """Скидає блокування API."""
        try:
            result = self.env['smartlogger.station'].reset_api_block()
            self.message = _("Блокування API скинуто успішно! Можете спробувати синхронізацію знову.")
            self.sync_status = 'success'

        except Exception as e:
            self.message = _("Помилка скидання блокування API: %s") % str(e)
            self.sync_status = 'error'

        return self._return_updated_form()

    def action_check_api_status(self):
        """Перевіряє статус API."""
        try:
            IrConfigParameter = self.env['ir.config_parameter'].sudo()

            api_blocked = IrConfigParameter.get_param('huawei.fusionsolar.api_blocked', 'false') == 'true'
            auth_error_count = int(IrConfigParameter.get_param('huawei.fusionsolar.auth_error_count', '0'))
            last_auth_error = IrConfigParameter.get_param('huawei.fusionsolar.last_auth_error', '')
            last_successful_sync = IrConfigParameter.get_param('huawei.fusionsolar.last_successful_sync', '')

            status_info = []
            if api_blocked:
                status_info.append("🔴 API ЗАБЛОКОВАНИЙ")
                status_info.append(f"Помилок автентифікації: {auth_error_count}")
                if last_auth_error:
                    status_info.append(f"Остання помилка: {last_auth_error}")
                status_info.append("Натисніть 'Скинути блокування' для відновлення")
            else:
                status_info.append("🟢 API активний")
                if auth_error_count > 0:
                    status_info.append(f"Попередніх помилок: {auth_error_count}")
                if last_successful_sync:
                    status_info.append(f"Остання успішна синхронізація: {last_successful_sync}")

            self.sync_results = "\n".join(status_info)
            self.sync_status = 'success' if not api_blocked else 'error'
            self.message = _("Статус API перевірено")

        except Exception as e:
            self.message = _("Помилка перевірки статусу: %s") % str(e)
            self.sync_status = 'error'

        return self._return_updated_form()

    def _validate_configuration(self):
        """Перевіряє конфігурацію API."""
        try:
            # Перевіряємо, чи не заблокований API
            self.env['smartlogger.station']._check_api_blocked_status()

            IrConfigParameter = self.env['ir.config_parameter'].sudo()
            username = IrConfigParameter.get_param('huawei.fusionsolar.username')
            password = IrConfigParameter.get_param('huawei.fusionsolar.password')
            base_url = IrConfigParameter.get_param('huawei.fusionsolar.base_url')

            if not username or not password:
                self.error_details = _("Відсутні облікові дані API (username/password)")
                return False

            if not base_url:
                self.error_details = _("Відсутній URL API сервера")
                return False

            return True

        except UserError as ue:
            # API заблокований
            self.error_details = str(ue)
            return False
        except Exception as e:
            _logger.error("Помилка валідації конфігурації: %s", e)
            self.error_details = str(e)
            return False

    def _perform_full_sync(self):
        """Виконує повну синхронізацію."""
        stations_model = self.env['smartlogger.station']

        if self.selected_station_ids:
            # Синхронізація тільки вибраних станцій
            _logger.info("Синхронізація %d вибраних станцій", len(self.selected_station_ids))
            return self._sync_selected_stations()
        else:
            # Повна синхронізація всіх станцій
            _logger.info("Повна синхронізація всіх станцій")
            return stations_model.sync_fusionsolar_data()

    def _perform_incremental_sync(self):
        """Виконує інкрементальну синхронізацію (тільки давно не оновлювані)."""
        stations_model = self.env['smartlogger.station']

        # Знаходимо станції, які не синхронізувалися більше години
        cutoff_time = datetime.now() - timedelta(hours=1)
        old_stations = stations_model.search([
            '|',
            ('last_sync', '<', cutoff_time),
            ('last_sync', '=', False)
        ])

        _logger.info("Інкрементальна синхронізація %d станцій", len(old_stations))

        if not old_stations:
            return {
                'success': True,
                'message': _("Всі станції мають актуальні дані"),
                'stations_processed': 0
            }

        # Використовуємо batch синхронізацію
        return self._sync_station_batch(old_stations)

    def _perform_stations_only_sync(self):
        """Оновлює тільки список станцій без KPI даних."""
        try:
            stations_model = self.env['smartlogger.station']
            base_url, username, password, batch_size, request_delay = stations_model._get_fusionsolar_api_credentials()

            # Викликаємо тільки оновлення списку станцій
            stations_model._update_station_list(base_url, username, password, request_delay)

            new_count = len(stations_model.search([('create_date', '>=', datetime.now() - timedelta(minutes=5))]))

            return {
                'success': True,
                'message': _("Список станцій оновлено"),
                'stations_created': new_count,
                'stations_processed': len(stations_model.search([]))
            }

        except Exception as e:
            _logger.error("Помилка синхронізації списку станцій: %s", e)
            raise

    def _perform_data_only_sync(self):
        """Оновлює тільки KPI дані існуючих станцій."""
        stations_model = self.env['smartlogger.station']

        existing_stations = stations_model.search([])
        if not existing_stations:
            raise UserError(_("Немає станцій для оновлення даних. Спочатку виконайте синхронізацію списку станцій."))

        _logger.info("Оновлення KPI даних для %d існуючих станцій", len(existing_stations))

        return self._sync_station_batch(existing_stations)

    def _sync_selected_stations(self):
        """Синхронізує тільки вибрані станції."""
        return self._sync_station_batch(self.selected_station_ids)

    def _sync_station_batch(self, stations):
        """Синхронізує пакет станцій."""
        if not stations:
            return {'success': True, 'stations_processed': 0}

        try:
            stations_model = self.env['smartlogger.station']
            base_url, username, password, batch_size, request_delay = stations_model._get_fusionsolar_api_credentials()

            # Використовуємо метод пакетної синхронізації
            stations_model._sync_stations_batch(base_url, username, password, batch_size, request_delay)

            return {
                'success': True,
                'message': _("Пакетна синхронізація завершена"),
                'stations_processed': len(stations)
            }

        except Exception as e:
            _logger.error("Помилка пакетної синхронізації: %s", e)
            raise

    def _process_sync_results(self, result, start_time):
        """Обробляє результати синхронізації."""
        duration = datetime.now() - start_time

        if result.get('success'):
            self.sync_status = 'success'

            # Оновлюємо статистику
            self.stations_found = result.get('stations_found', 0)
            self.stations_created = result.get('stations_created', 0)
            self.stations_updated = result.get('stations_updated', 0)
            self.stations_errors = result.get('stations_errors', 0)

            processed = result.get('stations_processed', 0)

            if self.stations_errors > 0:
                self.sync_status = 'partial_success'
                self.message = _(
                    "Синхронізація завершена частково. Оброблено: %d, Помилок: %d"
                ) % (processed, self.stations_errors)
            else:
                self.message = _(
                    "Синхронізація завершена успішно! Оброблено станцій: %d"
                ) % processed

            self.sync_details = self._format_sync_details(result, duration)

        else:
            self.sync_status = 'error'
            self.message = result.get('message', _("Помилка синхронізації"))
            self.error_details = result.get('details', '')

        self.last_sync_date = fields.Datetime.now()
        self.performance_stats = self._format_performance_stats(duration, result)

    def _format_sync_details(self, result, duration):
        """Форматує деталі синхронізації."""
        details = []
        details.append(f"Тривалість: {duration.total_seconds():.1f} сек")
        details.append(f"Режим синхронізації: {dict(self._fields['sync_mode'].selection)[self.sync_mode]}")

        if result.get('stations_found'):
            details.append(f"Станцій знайдено в API: {result['stations_found']}")
        if result.get('stations_created'):
            details.append(f"Нових станцій створено: {result['stations_created']}")
        if result.get('stations_updated'):
            details.append(f"Станцій оновлено: {result['stations_updated']}")
        if result.get('api_calls_made'):
            details.append(f"API викликів зроблено: {result['api_calls_made']}")

        return "\n".join(details)

    def _format_performance_stats(self, duration, result):
        """Форматує статистику продуктивності."""
        stats = []
        stats.append(f"Загальний час: {duration.total_seconds():.2f} сек")

        processed = result.get('stations_processed', 0)
        if processed > 0:
            avg_time = duration.total_seconds() / processed
            stats.append(f"Середній час на станцію: {avg_time:.2f} сек")

        api_calls = result.get('api_calls_made', 0)
        if api_calls > 0:
            stats.append(f"API викликів: {api_calls}")
            avg_api_time = duration.total_seconds() / api_calls
            stats.append(f"Середній час API виклику: {avg_api_time:.2f} сек")

        return "\n".join(stats)

    def _handle_sync_error(self, error_msg, start_time, unexpected=False):
        """Обробляє помилки синхронізації."""
        duration = datetime.now() - start_time

        self.sync_status = 'error'

        if unexpected:
            self.message = _("Неочікувана помилка під час синхронізації: %s") % error_msg
            _logger.error("Неочікувана помилка синхронізації SmartLogger: %s", error_msg, exc_info=True)
        else:
            self.message = error_msg
            _logger.error("Помилка синхронізації SmartLogger: %s", error_msg)

        self.error_details = error_msg
        self.performance_stats = f"Тривалість до помилки: {duration.total_seconds():.2f} сек"

        return self._return_updated_form()

    def _return_error_result(self, error_msg):
        """Повертає результат з помилкою."""
        self.sync_status = 'error'
        self.message = error_msg
        return self._return_updated_form()

    def _return_updated_form(self):
        """Повертає оновлену форму майстра."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'smartlogger.sync.data.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_close(self):
        """Закриває майстер."""
        return {'type': 'ir.actions.act_window_close'}

    def action_view_stations(self):
        """Відкриває список станцій."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Станції SmartLogger'),
            'res_model': 'smartlogger.station',
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_view_errors(self):
        """Відкриває список станцій з помилками."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Станції з помилками синхронізації'),
            'res_model': 'smartlogger.station',
            'view_mode': 'tree,form',
            'domain': [('status', 'in', ['error', 'sync_error'])],
            'target': 'current',
        }

    def action_retry_failed(self):
        """Повторна спроба синхронізації для станцій з помилками."""
        failed_stations = self.env['smartlogger.station'].search([
            ('status', 'in', ['error', 'sync_error'])
        ])

        if not failed_stations:
            self.message = _("Немає станцій з помилками для повтору")
            return self._return_updated_form()

        self.selected_station_ids = [(6, 0, failed_stations.ids)]
        self.sync_mode = 'data_only'

        return self.action_sync_now()

    def action_cleanup_old_data(self):
        """Очищення старих KPI даних."""
        try:
            IrConfigParameter = self.env['ir.config_parameter'].sudo()
            retention_days = int(IrConfigParameter.get_param('huawei.fusionsolar.data_retention_days', '90'))

            deleted_count = self.env['smartlogger.station'].cleanup_old_kpi_data(retention_days)

            self.message = _("Очищено %d старих записів KPI (старіше %d днів)") % (deleted_count, retention_days)
            self.sync_status = 'success'

        except Exception as e:
            self.message = _("Помилка очищення даних: %s") % str(e)
            self.sync_status = 'error'

        return self._return_updated_form()

    def action_show_system_info(self):
        """Показує інформацію про систему."""
        try:
            stations = self.env['smartlogger.station'].search([])

            # Статистика станцій
            total_stations = len(stations)
            active_stations = len(stations.filtered(lambda s: s.status == 'active'))
            error_stations = len(stations.filtered(lambda s: s.status in ['error', 'sync_error']))

            # Статистика KPI даних
            kpi_records = self.env['smartlogger.data'].search([])
            total_kpi_records = len(kpi_records)

            # Останні синхронізації
            recent_syncs = stations.filtered('last_sync').sorted('last_sync', reverse=True)
            last_sync = recent_syncs[0].last_sync if recent_syncs else False

            # Формуємо звіт
            info = []
            info.append(f"📊 Загальна статистика:")
            info.append(f"   • Всього станцій: {total_stations}")
            info.append(f"   • Активних: {active_stations}")
            info.append(f"   • З помилками: {error_stations}")
            info.append(f"   • Записів KPI: {total_kpi_records}")
            info.append(f"")
            info.append(f"🔄 Синхронізація:")
            if last_sync:
                info.append(f"   • Остання: {last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                info.append(f"   • Ніколи не виконувалась")
            info.append(f"")
            info.append(f"💾 База даних:")
            info.append(f"   • Модель станцій: smartlogger.station")
            info.append(f"   • Модель KPI: smartlogger.data")

            self.sync_results = "\n".join(info)
            self.sync_status = 'success'
            self.message = _("Інформація про систему оновлена")

        except Exception as e:
            self.message = _("Помилка отримання інформації: %s") % str(e)
            self.sync_status = 'error'

        return self._return_updated_form()