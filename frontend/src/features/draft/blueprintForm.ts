import type { components } from "../../api/generated/schema";

type DraftView = components["schemas"]["DraftView"];
type BlueprintPresentationInput = components["schemas"]["BlueprintPresentationInput"];
type BlueprintGameplayInput = components["schemas"]["BlueprintGameplayInput"];
type BlueprintBuffInput = components["schemas"]["BlueprintBuffInput"];
type RecipeUnlock = components["schemas"]["RecipeUnlock"];

export type BlueprintIngredientRow = {
  itemId: string;
  displayName: string;
  quantity: number;
  mappingReason: string;
  catalogVersion: string;
};

export type BlueprintFormValues = {
  displayName: string;
  internalName: string;
  categoryLabel: string;
  description: string;
  tags: string;
  ingredients: BlueprintIngredientRow[];
  edibility: number;
  sellPrice: number;
  isDrink: boolean;
  recipeUnlock: RecipeUnlock;
  buff: BlueprintBuffInput | null;
};

type DraftGameplay = NonNullable<DraftView["gameplay"]>;
type DraftBuff = DraftGameplay["buff"];

export function buffToInput(buff: DraftBuff): BlueprintBuffInput | null {
  if (!buff) {
    return null;
  }
  return {
    id: buff.id,
    durationMinutes: buff.durationMinutes,
    isDebuff: buff.isDebuff,
    attributes: {
      farmingLevel: buff.attributes.farmingLevel,
      fishingLevel: buff.attributes.fishingLevel,
      miningLevel: buff.attributes.miningLevel,
      foragingLevel: buff.attributes.foragingLevel,
      combatLevel: buff.attributes.combatLevel,
      luckLevel: buff.attributes.luckLevel,
      attack: buff.attributes.attack,
      defense: buff.attributes.defense,
      immunity: buff.attributes.immunity,
      magneticRadius: buff.attributes.magneticRadius,
      maxStamina: buff.attributes.maxStamina,
      speed: buff.attributes.speed,
    },
  };
}

export function fromDraftView(draft: DraftView): BlueprintFormValues {
  const presentation = draft.presentation;
  const gameplay = draft.gameplay;
  return {
    displayName: presentation?.displayName ?? "",
    internalName: presentation?.internalName ?? "",
    categoryLabel: presentation?.categoryLabel ?? "",
    description: presentation?.description ?? "",
    tags: presentation?.tags?.join(", ") ?? "",
    ingredients:
      gameplay?.ingredients.map((ingredient) => ({
        itemId: ingredient.itemId,
        displayName: ingredient.displayName,
        quantity: ingredient.quantity,
        mappingReason: ingredient.mappingReason,
        catalogVersion: ingredient.catalogVersion,
      })) ?? [],
    edibility: gameplay?.recovery.edibility ?? 0,
    sellPrice: gameplay?.sellPrice ?? 0,
    isDrink: gameplay?.isDrink ?? false,
    recipeUnlock: gameplay?.recipeUnlock ?? "DEFAULT",
    buff: buffToInput(gameplay?.buff ?? null),
  };
}

export function toPatchInput(values: BlueprintFormValues): {
  presentation: BlueprintPresentationInput;
  gameplay: BlueprintGameplayInput;
} {
  return {
    presentation: {
      displayName: values.displayName,
      internalName: values.internalName,
      categoryLabel: values.categoryLabel,
      description: values.description,
      tags: values.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    },
    gameplay: {
      ingredients: values.ingredients,
      recovery: { edibility: values.edibility },
      sellPrice: values.sellPrice,
      isDrink: values.isDrink,
      recipeUnlock: values.recipeUnlock,
      buff: values.buff,
    },
  };
}
