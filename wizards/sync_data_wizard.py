# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SyncDataWizard(models.TransientModel):
    _name = 'smartlogger.sync.data.wizard'
    _description = 'Майстер синхронізації даних SmartLogger'

    # Поле для відображення повідомлення користувачу
    message = fields.Char(string='Статус', readonly=True)

    # Додаткові поля для більш детальної інформації
    sync_status = fields.Selection([
        ('waiting', 'Очікування'),
        ('running', 'Виконується'),
        ('success', 'Успішно'),
        ('error', 'Помилка')
    ], string='Статус синхронізації', default='waiting', readonly=True)

    last_sync_date = fields.Datetime(string='Остання синхронізація', readonly=True)
    sync_details = fields.Text(string='Деталі синхронізації', readonly=True)

    @api.model
    def default_get(self, fields_list):
        """
        Встановлює значення за замовчуванням при відкритті майстра.
        """
        res = super(SyncDataWizard, self).default_get(fields_list)

        # Отримуємо інформацію про останню синхронізацію
        try:
            stations = self.env['smartlogger.station'].search([])
            if stations:
                last_sync = fields.Datetime.now()
                res['last_sync_date'] = last_sync
                res['message'] = _("Готовий до синхронізації. Остання синхронізація: %s") % last_sync
            else:
                res['message'] = _("Станції не знайдено. Переконайтеся, що станції налаштовані.")
        except Exception as e:
            _logger.warning("Помилка при отриманні інформації про останню синхронізацію: %s", e)
            res['message'] = _("Готовий до синхронізації")

        return res

    def action_sync_now(self):
        """
        Запускає синхронізацію даних FusionSolar негайно.
        """
        self.sync_status = 'running'
        self.message = _("Синхронізація розпочата...")

        try:
            # Перевіряємо наявність станцій
            stations = self.env['smartlogger.station'].search([])
            if not stations:
                raise UserError(_("Не знайдено жодної станції для синхронізації. Спочатку налаштуйте станції."))

            _logger.info("Запуск синхронізації SmartLogger для %d станцій", len(stations))

            # Викликаємо метод синхронізації з моделі smartlogger.station
            sync_result = self.env['smartlogger.station'].sync_fusionsolar_data()

            # Обробляємо результат синхронізації
            if isinstance(sync_result, dict):
                success_count = sync_result.get('success', 0)
                error_count = sync_result.get('errors', 0)

                if error_count == 0:
                    self.sync_status = 'success'
                    self.message = _("Синхронізація завершена успішно! Оброблено станцій: %d") % success_count
                    self.sync_details = _("Успішно синхронізовано: %d станцій") % success_count
                else:
                    self.sync_status = 'error'
                    self.message = _("Синхронізація завершена з помилками. Успішно: %d, З помилками: %d") % (success_count, error_count)
                    self.sync_details = sync_result.get('details', '')
            else:
                self.sync_status = 'success'
                self.message = _("Синхронізація даних запущена успішно. Перевірте логи або оновіть сторінку станцій.")
                self.sync_details = _("Синхронізація виконана")

            self.last_sync_date = fields.Datetime.now()
            _logger.info("Синхронізація SmartLogger завершена успішно")

        except UserError as e:
            self.sync_status = 'error'
            self.message = str(e)
            self.sync_details = _("UserError: %s") % str(e)
            _logger.error("UserError під час синхронізації SmartLogger: %s", e)

        except Exception as e:
            self.sync_status = 'error'
            error_msg = _("Виникла неочікувана помилка під час запуску синхронізації: %s") % str(e)
            self.message = error_msg
            self.sync_details = _("Exception: %s") % str(e)
            _logger.error("Неочікувана помилка під час синхронізації SmartLogger: %s", e, exc_info=True)

        # Повертаємо оновлену форму майстра
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'smartlogger.sync.data.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_close(self):
        """
        Закриває майстер та повертає до попереднього вікна.
        """
        return {'type': 'ir.actions.act_window_close'}

    def action_view_stations(self):
        """
        Відкриває список станцій для перегляду результатів синхронізації.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Станції SmartLogger'),
            'res_model': 'smartlogger.station',
            'view_mode': 'tree,form',
            'target': 'current',
        }