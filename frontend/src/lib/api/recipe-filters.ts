import { z } from 'zod';

export const keywordCategories = [
	'cuisine_region',
	'course',
	'dish_type',
	'key_ingredient',
	'method'
] as const;
export const categoryLabels: Record<string, string> = {
	cuisine_region: 'Cuisine / region',
	course: 'Course',
	dish_type: 'Dish type',
	key_ingredient: 'Key ingredient',
	method: 'Method'
};
export const filterFields = [
	'name',
	'alternate_name',
	'summary',
	'description',
	'ingredients',
	'instructions',
	'keyword',
	...keywordCategories,
	'book',
	'author',
	'favourite',
	'list',
	'has_image'
] as const;
export type FilterField = (typeof filterFields)[number];
export const fieldLabels: Record<FilterField, string> = {
	name: 'Recipe name',
	alternate_name: 'Alternate name',
	summary: 'Summary',
	description: 'Description',
	ingredients: 'Ingredient text',
	instructions: 'Instruction text',
	keyword: 'Any keyword',
	cuisine_region: 'Cuisine / region',
	course: 'Course',
	dish_type: 'Dish type',
	key_ingredient: 'Key ingredient',
	method: 'Method',
	book: 'Book',
	author: 'Author',
	favourite: 'Favourite',
	list: 'List membership',
	has_image: 'Recipe image'
};
export const operatorLabels = {
	eq: 'equals',
	neq: 'does not equal',
	contains: 'contains',
	not_contains: 'does not contain',
	starts_with: 'starts with',
	ends_with: 'ends with',
	is_empty: 'is empty',
	is_not_empty: 'is not empty',
	in_list: 'in list',
	not_in_list: 'not in list'
};
export type FilterOperator = keyof typeof operatorLabels;
const textOperators: FilterOperator[] = [
	'eq',
	'neq',
	'contains',
	'not_contains',
	'starts_with',
	'ends_with',
	'is_empty',
	'is_not_empty'
];
export function operatorsFor(field: FilterField): FilterOperator[] {
	if (field === 'favourite' || field === 'has_image') return ['eq'];
	if (field === 'list') return ['in_list', 'not_in_list'];
	if (field === 'book') return textOperators.filter((o) => !o.startsWith('is_'));
	return textOperators;
}
export const ruleSchema = z
	.object({
		field: z.enum(filterFields),
		operator: z.enum([
			'eq',
			'neq',
			'contains',
			'not_contains',
			'starts_with',
			'ends_with',
			'is_empty',
			'is_not_empty',
			'in_list',
			'not_in_list'
		]),
		value: z.union([z.string(), z.boolean(), z.null()]).optional()
	})
	.strict()
	.superRefine((rule, ctx) => {
		const fail = (message: string) => ctx.addIssue({ code: z.ZodIssueCode.custom, message });
		if (!operatorsFor(rule.field).includes(rule.operator))
			return fail('Choose an operator for this field.');
		if (rule.field === 'favourite' || rule.field === 'has_image') {
			if (typeof rule.value !== 'boolean') fail('Choose yes or no.');
		} else if (rule.operator === 'is_empty' || rule.operator === 'is_not_empty') {
			if (rule.value != null) fail('Empty checks do not take a value.');
		} else if (typeof rule.value !== 'string' || !rule.value.trim() || rule.value.length > 500) {
			fail('Enter a value between 1 and 500 characters.');
		} else if (
			rule.field === 'list' ||
			(rule.field === 'book' && ['eq', 'neq'].includes(rule.operator))
		) {
			if (!z.string().uuid().safeParse(rule.value).success)
				fail('Select a book or list from the suggestions.');
		}
	});
export const recipeFiltersSchema = z
	.object({
		version: z.literal(1),
		match: z.enum(['all', 'any']),
		rules: z.array(ruleSchema).max(20)
	})
	.strict();
export type FilterRule = z.infer<typeof ruleSchema>;
export type RecipeFilters = z.infer<typeof recipeFiltersSchema>;
export const emptyFilters = (): RecipeFilters => ({ version: 1, match: 'all', rules: [] });
export const normaliseFilters = (filters: RecipeFilters): RecipeFilters => ({
	...filters,
	rules: filters.rules.map((rule) => ({
		...rule,
		value: typeof rule.value === 'string' ? rule.value.trim() : (rule.value ?? null)
	}))
});
export function ruleLabel(
	rule: FilterRule,
	books: { id: string; title: string }[] = [],
	lists: { id: string; name: string }[] = []
): string {
	if (rule.field === 'favourite') return rule.value ? 'Is favourite' : 'Is not favourite';
	if (rule.field === 'has_image') return rule.value ? 'Has image' : 'No image';
	let value = String(rule.value ?? '');
	if (rule.field === 'book' && ['eq', 'neq'].includes(rule.operator))
		value = books.find((b) => b.id === value)?.title ?? 'Unavailable book';
	if (rule.field === 'list') value = lists.find((l) => l.id === value)?.name ?? 'Unavailable list';
	return `${fieldLabels[rule.field]} ${operatorLabels[rule.operator]}${value ? ` “${value}”` : ''}`;
}
