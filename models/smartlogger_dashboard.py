# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import json
import logging

_logger = logging.getLogger(__name__)


class SmartLoggerDashboard(models.Model):
    _name = 'smartlogger.dashboard'
    _description = 'Дашборд SmartLogger'
    _auto = False  # Ця модель не створює таблицю в базі даних

    # Поля для відображення (не зберігаються в БД)
    total_stations = fields.Integer(string='Загальна кількість станцій')
    total_capacity = fields.Float(string='Загальна потужність (кВт)')
    current_total_power = fields.Float(string='Поточна загальна потужність (кВт)')
    daily_total_energy = fields.Float(string='Добова загальна енергія (кВт·год)')

    @api.model
    def default_get(self, fields_list):
        """Заповнення полів дашборду поточними даними"""
        res = super().default_get(fields_list)
        dashboard_data = self.get_dashboard_data()

        res.update({
            'total_stations': dashboard_data.get('total_stations', 0),
            'total_capacity': dashboard_data.get('total_capacity', 0.0),
            'current_total_power': dashboard_data.get('current_total_power', 0.0),
            'daily_total_energy': dashboard_data.get('daily_total_energy', 0.0),
        })

        return res

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Переоизначає search_read для віртуальної моделі"""
        dashboard_data = self.get_dashboard_data()

        record = {
            'id': 1,  # Фіктивний ID
            'total_stations': dashboard_data.get('total_stations', 0),
            'total_capacity': dashboard_data.get('total_capacity', 0.0),
            'current_total_power': dashboard_data.get('current_total_power', 0.0),
            'daily_total_energy': dashboard_data.get('daily_total_energy', 0.0),
        }

        if fields:
            record = {key: record[key] for key in fields if key in record}

        return [record]

    def read(self, fields=None, load='_classic_read'):
        """Переоизначає read для віртуальної моделі"""
        dashboard_data = self.get_dashboard_data()

        record = {
            'id': 1,
            'total_stations': dashboard_data.get('total_stations', 0),
            'total_capacity': dashboard_data.get('total_capacity', 0.0),
            'current_total_power': dashboard_data.get('current_total_power', 0.0),
            'daily_total_energy': dashboard_data.get('daily_total_energy', 0.0),
        }

        if fields:
            record = {key: record[key] for key in fields if key in record}

        return [record]

    @api.model
    def load(self, fields, data):
        """Переоизначає load для віртуальної моделі"""
        return {
            'ids': [1],
            'messages': []
        }

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Переоизначає fields_get для віртуальної моделі"""
        res = super().fields_get(allfields, attributes)
        return res

    @api.model
    def get_dashboard_data(self, filter_params=None):
        """
        Отримує агреговані дані для дашборду SmartLogger.

        Args:
            filter_params (dict): Параметри фільтрації (опційно)
                - station_ids: список ID станцій
                - date_from: дата початку періоду
                - date_to: дата кінця періоду
                - status: статус станцій

        Returns:
            dict: Агреговані дані для дашборду
        """
        try:
            # Базовий домен для пошуку станцій
            domain = []

            # Застосування фільтрів
            if filter_params:
                if filter_params.get('station_ids'):
                    domain.append(('id', 'in', filter_params['station_ids']))
                if filter_params.get('status'):
                    domain.append(('status', '=', filter_params['status']))

            stations = self.env['smartlogger.station'].search(domain)

            # Базові агрегати
            dashboard_data = self._calculate_basic_metrics(stations)

            # Додаткові метрики
            dashboard_data.update(self._calculate_performance_metrics(stations))

            # Деталі станцій
            dashboard_data['stations_summary'] = self._get_stations_summary(stations)

            # Історичні дані
            dashboard_data['historical_data'] = self._get_historical_trends(
                stations, filter_params
            )

            # Алерти та попередження
            dashboard_data['alerts'] = self._get_system_alerts(stations)

            # Статистика по статусах
            dashboard_data['status_breakdown'] = self._get_status_breakdown(stations)

            dashboard_data['last_update_time'] = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            dashboard_data['filter_applied'] = bool(filter_params)

            return dashboard_data

        except Exception as e:
            _logger.error(f"Помилка при отриманні даних дашборду: {str(e)}")
            raise UserError(_("Помилка при завантаженні даних дашборду: %s") % str(e))

    def _calculate_basic_metrics(self, stations):
        """Обчислює базові метрики дашборду"""
        total_capacity = sum(stations.mapped('capacity'))
        current_total_power = sum(stations.mapped('current_power'))
        daily_total_energy = sum(stations.mapped('daily_energy'))
        monthly_total_energy = sum(stations.mapped('monthly_energy'))
        yearly_total_energy = sum(stations.mapped('yearly_energy'))
        lifetime_total_energy = sum(stations.mapped('lifetime_energy'))

        return {
            'total_stations': len(stations),
            'total_capacity': total_capacity,
            'current_total_power': current_total_power,
            'daily_total_energy': daily_total_energy,
            'monthly_total_energy': monthly_total_energy,
            'yearly_total_energy': yearly_total_energy,
            'lifetime_total_energy': lifetime_total_energy,
        }

    def _calculate_performance_metrics(self, stations):
        """Обчислює метрики продуктивності"""
        total_capacity = sum(stations.mapped('capacity'))
        current_total_power = sum(stations.mapped('current_power'))

        # Ефективність системи
        system_efficiency = (current_total_power / total_capacity * 100) if total_capacity > 0 else 0

        # Активні станції
        active_stations = stations.filtered(lambda s: s.status == 'active')
        active_percentage = (len(active_stations) / len(stations) * 100) if stations else 0

        # Середня потужність на станцію
        avg_power_per_station = current_total_power / len(stations) if stations else 0

        return {
            'system_efficiency': round(system_efficiency, 2),
            'active_stations_count': len(active_stations),
            'active_percentage': round(active_percentage, 2),
            'avg_power_per_station': round(avg_power_per_station, 2),
        }

    def _get_stations_summary(self, stations):
        """Отримує зведення по станціях"""
        stations_summary = []
        for station in stations:
            efficiency = 0
            if station.capacity > 0:
                efficiency = (station.current_power / station.capacity) * 100

            stations_summary.append({
                'id': station.id,
                'name': station.name,
                'station_code': station.station_code,
                'capacity': station.capacity,
                'current_power': station.current_power,
                'daily_energy': station.daily_energy,
                'efficiency': round(efficiency, 2),
                'status': station.status,
                'last_sync': station.last_sync.strftime('%Y-%m-%d %H:%M:%S') if station.last_sync else False,
            })

        return stations_summary

    def _get_historical_trends(self, stations, filter_params):
        """Отримує історичні тенденції"""
        if not stations:
            return []

        # Параметри періоду
        date_to = datetime.now()
        date_from = date_to - timedelta(days=7)  # За замовчуванням 7 днів

        if filter_params:
            if filter_params.get('date_from'):
                date_from = datetime.strptime(filter_params['date_from'], '%Y-%m-%d')
            if filter_params.get('date_to'):
                date_to = datetime.strptime(filter_params['date_to'], '%Y-%m-%d')

        # Запит історичних даних
        domain = [
            ('station_id', 'in', stations.ids),
            ('timestamp', '>=', date_from),
            ('timestamp', '<=', date_to)
        ]

        historical_records = self.env['smartlogger.data'].search(domain, order='timestamp ASC')

        # Групування по датах
        daily_data = {}
        for record in historical_records:
            date_key = record.timestamp.strftime('%Y-%m-%d')
            if date_key not in daily_data:
                daily_data[date_key] = {
                    'date': date_key,
                    'total_power': 0,
                    'total_energy': 0,
                    'record_count': 0
                }
            daily_data[date_key]['total_power'] += record.current_power
            daily_data[date_key]['total_energy'] += record.daily_energy
            daily_data[date_key]['record_count'] += 1

        # Перетворення в список
        trends = []
        for date_key in sorted(daily_data.keys()):
            data = daily_data[date_key]
            trends.append({
                'date': date_key,
                'avg_power': round(data['total_power'] / data['record_count'], 2) if data['record_count'] > 0 else 0,
                'total_energy': round(data['total_energy'], 2)
            })

        return trends

    def _get_system_alerts(self, stations):
        """Отримує системні алерти"""
        alerts = []
        current_time = datetime.now()

        for station in stations:
            # Алерт про відсутність синхронізації
            if station.last_sync:
                sync_delay = current_time - station.last_sync
                if sync_delay.total_seconds() > 3600:  # Більше 1 години
                    alerts.append({
                        'type': 'warning',
                        'station_id': station.id,
                        'station_name': station.name,
                        'message': f'Остання синхронізація: {sync_delay.seconds // 3600} год. тому'
                    })

            # Алерт про низьку ефективність
            if station.capacity > 0:
                efficiency = (station.current_power / station.capacity) * 100
                if efficiency < 50:  # Менше 50% ефективності
                    alerts.append({
                        'type': 'error',
                        'station_id': station.id,
                        'station_name': station.name,
                        'message': f'Низька ефективність: {efficiency:.1f}%'
                    })

            # Алерт про статус - ВИПРАВЛЕНО
            if hasattr(station, 'status') and station.status in ['error', 'maintenance']:
                # Отримуємо словник вибору статусів
                status_field = station._fields.get('status')
                if status_field and hasattr(status_field, 'selection'):
                    status_selection = dict(status_field.selection)
                    status_label = status_selection.get(station.status, station.status)
                else:
                    status_label = station.status

                alerts.append({
                    'type': 'error' if station.status == 'error' else 'info',
                    'station_id': station.id,
                    'station_name': station.name,
                    'message': f'Статус: {status_label}'
                })

        return alerts

    def _get_status_breakdown(self, stations):
        """Отримує розподіл станцій по статусах"""
        status_counts = {}

        # Перевіряємо, чи існує поле status
        if hasattr(self.env['smartlogger.station'], '_fields') and 'status' in self.env['smartlogger.station']._fields:
            status_field = self.env['smartlogger.station']._fields['status']
            if hasattr(status_field, 'selection'):
                status_selection = dict(status_field.selection)
            else:
                status_selection = {}
        else:
            status_selection = {}

        for station in stations:
            status = getattr(station, 'status', 'unknown')
            if status not in status_counts:
                status_counts[status] = 0
            status_counts[status] += 1

        breakdown = []
        for status, count in status_counts.items():
            breakdown.append({
                'status': status,
                'status_label': status_selection.get(status, status),
                'count': count,
                'percentage': round((count / len(stations)) * 100, 1) if stations else 0
            })

        return breakdown

    @api.model
    def get_station_details(self, station_id):
        """Отримує детальну інформацію про станцію"""
        station = self.env['smartlogger.station'].browse(station_id)
        if not station.exists():
            raise UserError(_("Станція не знайдена"))

        # Останні записи KPI
        recent_data = self.env['smartlogger.data'].search([
            ('station_id', '=', station_id)
        ], order='timestamp DESC', limit=10)

        # Статистика за період
        date_from = datetime.now() - timedelta(days=30)
        period_data = self.env['smartlogger.data'].search([
            ('station_id', '=', station_id),
            ('timestamp', '>=', date_from)
        ])

        avg_power = sum(period_data.mapped('current_power')) / len(period_data) if period_data else 0
        max_power = max(period_data.mapped('current_power')) if period_data else 0

        return {
            'station_info': {
                'id': station.id,
                'name': station.name,
                'station_code': station.station_code,
                'capacity': station.capacity,
                'current_power': station.current_power,
                'status': getattr(station, 'status', 'unknown'),
                'last_sync': station.last_sync.strftime('%Y-%m-%d %H:%M:%S') if station.last_sync else False,
            },
            'recent_data': [{
                'timestamp': record.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'current_power': record.current_power,
                'daily_energy': record.daily_energy,
            } for record in recent_data],
            'period_stats': {
                'avg_power': round(avg_power, 2),
                'max_power': round(max_power, 2),
                'total_records': len(period_data),
            }
        }

    @api.model
    def export_dashboard_data(self, format_type='json'):
        """Експортує дані дашборду в різних форматах"""
        dashboard_data = self.get_dashboard_data()

        if format_type == 'json':
            return json.dumps(dashboard_data, indent=2, default=str)
        elif format_type == 'csv':
            # Реалізація експорту в CSV
            pass

        return dashboard_data