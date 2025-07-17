# -*- coding: utf-8 -*-
# ФАЙЛ: __manifest__.py

# Маніфест модуля Odoo
{
    'name': "Huawei SmartLogger Integration",

    'summary': """
        Професійна інтеграція з Huawei FusionSolar API для множественних сонячних станцій.
    """,

    'description': """

                                              Повнофункціональний модуль для інтеграції з Huawei FusionSolar API:

                                              🔹 Підтримка множественних станцій з пагінацією
        🔹 Пакетна обробка для оптимізації API запитів  
        🔹 Розширена статистика та аналітика
        🔹 Автоматична синхронізація з налаштуваннями
        🔹 Інтелектуальна обробка помилок та повторні спроби
        🔹 Гнучкі налаштування продуктивності
        🔹 Автоматичне очищення історичних даних
        🔹 Детальна аналітика ефективності станцій
        🔹 Підтримка різних регіональних API endpoints
        🔹 Kanban, списки та форми для зручного управління

        Включає:
        - Автоматичну синхронізацію через Cron (кожні 15 хвилин)
        - Ручну синхронізацію через зручний майстер
        - Дашборд з аналітикою по всіх станціях
        - Історичні дані KPI з можливістю фільтрації
        - Розширені налаштування API для оптимізації
    """,

    'author': "Ярослав Гришин/HD Group LLC",
    'website': "https://www.hlibodar.com.ua",

    'category': 'Operations/IoT',
    'version': '2.0.1',

    # Залежності модуля
    'depends': ['base', 'mail'],

    'data': [
        'security/ir.model.access.csv',
        'views/000_menu.xml',
        'data/config_data.xml',
        'views/smartlogger_config_views.xml',
        'views/smartlogger_action.xml',
        'views/smartlogger_additional_actions.xml',
        'views/smartlogger_data_views.xml',
        'views/smartlogger_station_views.xml',
        'views/smartlogger_dashboard_views.xml',
        'wizards/sync_data_wizard_views.xml',
        'data/cron_data.xml',
        'views/zzz_menu.xml',
    ],

    # Демо дані (опціонально)
    'demo': [
        # 'demo/demo_stations.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',

    # Додаткові характеристики
    'images': ['static/descriptions/banner.png'],
    'price': 0,
    'currency': 'EUR',

    # Зовнішні залежності
    'external_dependencies': {
        'python': ['requests'],
    },

}
