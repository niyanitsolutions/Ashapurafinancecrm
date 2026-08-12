"""Dashboard Framework constants. `category` on widgets/nav items is free text (same
data-driven philosophy as Access Control's module/resource — see decision 021) since
future modules will introduce their own groupings. `WidgetType` is a small fixed
rendering hint, not a business concept, so it's a closed set."""


class WidgetType:
    METRIC = "metric"
    LIST = "list"

    ALL = (METRIC, LIST)
