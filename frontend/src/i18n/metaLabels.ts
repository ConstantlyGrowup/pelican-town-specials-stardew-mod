import type { Language } from "./copy";

/**
 * The Blueprint editor stores the curated Chinese category/tag values as the
 * canonical draft data (they feed generation prompts and archives), so the
 * locale switch must only affect presentation. These maps translate the
 * curated option values from `application/meta.py` into English labels.
 */
const DISH_CATEGORY_LABELS: Record<string, string> = {
  主菜: "Main Dish",
  汤类: "Soup",
  小吃: "Snack",
  甜品: "Dessert",
  饮品: "Drink",
  早餐: "Breakfast",
  沙拉: "Salad",
  主食: "Staple Food",
  配菜: "Side Dish",
  节日大餐: "Holiday Feast",
};

const DISH_TAG_LABELS: Record<string, string> = {
  家常: "Home-style",
  清淡: "Light",
  香辣: "Spicy",
  酸甜: "Sweet & Sour",
  咸鲜: "Savory",
  浓郁: "Rich",
  清爽: "Refreshing",
  暖胃: "Warming",
  节日: "Festive",
  春夏: "Spring & Summer",
  秋冬: "Fall & Winter",
  面食: "Noodles",
  米饭: "Rice",
  素食: "Vegetarian",
  鱼肉: "Fish",
  禽蛋: "Poultry & Eggs",
  奶香: "Creamy",
};

/**
 * Resolve the display label for a curated category/tag value.
 * Free-form values (for example tags authored by Ask Gus) have no curated
 * English translation and fall back to the stored value unchanged.
 */
export function metaDisplayLabel(value: string, locale: Language): string {
  if (locale !== "en-US") {
    return value;
  }
  return DISH_CATEGORY_LABELS[value] ?? DISH_TAG_LABELS[value] ?? value;
}
