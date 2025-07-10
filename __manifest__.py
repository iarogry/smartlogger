# -*- coding: utf-8 -*-
# Маніфест модуля Odoo
{
    'name': "Huawei SmartLogger Integration",

    'summary': """
        Автоматична синхронізація даних сонячних станцій з Huawei FusionSolar API.
    """,

    'description': """
        Цей модуль інтегрується з Huawei FusionSolar API для отримання даних про сонячні станції,
        їхню поточну потужність та генерацію (щоденну, місячну, річну, загальну).
        Включає автоматичну синхронізацію через Cron та ручну синхронізацію через майстер.
    """,

    'author': "Ярослав Гришин/HD Group LLC",
    'website': "http://www.hlibodar.com.ua",

    'category': 'Operations/IoT',
    'version': '1.0',

    # Залежності модуля (base для базових функцій, mail для чату та сповіщень)
    'depends': ['base', 'mail'],

    'data': [
        # Права доступу
        'security/ir_model_access.csv',
        # Дані для Cron-завдання
        'data/cron_data.xml',
        # Відображення для станцій
        'views/smartlogger_station_views.xml',
        # Відображення для історичних даних
        'views/smartlogger_data_views.xml',
        # Відображення для дашборду
        'views/smartlogger_dashboard_views.xml',
        # Відображення для майстра синхронізації
        'wizards/sync_data_wizard_views.xml',
        # Визначення меню модуля
        'views/menu.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}