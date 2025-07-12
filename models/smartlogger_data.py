# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SmartLoggerData(models.Model):
    _name = 'smartlogger.data'
    _description = 'Історичні дані SmartLogger KPI'
    _order = 'timestamp DESC' # Сортування за часом у спадному порядку

    station_id = fields.Many2one('smartlogger.station', string='Станція', required=True, ondelete='cascade')
    timestamp = fields.Datetime('Час запису', default=fields.Datetime.now, required=True, index=True)
    current_power = fields.Float('Поточна потужність (кВт)')
    daily_energy = fields.Float('Добова енергія (кВт·год)')
    monthly_energy = fields.Float('Місячна енергія (кВт·год)')
    yearly_energy = fields.Float('Річна енергія (кВт·год)')
    lifetime_energy = fields.Float('Загальна енергія (кВт·год)')

    _sql_constraints = [
        ('station_timestamp_unique', 'unique(station_id, timestamp)', 'Запис KPI для цієї станції та часу вже існує!'),
    ]