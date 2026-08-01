import type { Check, Verifier } from '../types';

function accessibleName(el: Element): string {
	return (
		el.getAttribute('aria-label') ??
		el.getAttribute('title') ??
		el.textContent?.trim() ??
		''
	);
}

/** Accessibility checks (DESIGN §8 makes these load-bearing): named controls,
 *  labelled inputs, alt text. Real violations `fail` the verdict — they are not
 *  advisory. An intentionally-decorative image still passes (it carries alt=""). */
export const a11y: Verifier = {
	id: 'a11y',
	description: 'Buttons named, inputs labelled, images have alt text',
	run({ root }): Check[] {
		const checks: Check[] = [];

		const unnamedButtons = Array.from(root.querySelectorAll('button')).filter(
			(b) => accessibleName(b) === ''
		);
		checks.push(
			unnamedButtons.length === 0
				? { verifier: 'a11y', status: 'ok', label: 'buttons named' }
				: { verifier: 'a11y', status: 'fail', label: `${unnamedButtons.length} unnamed button(s)` }
		);

		const unlabelledInputs = Array.from(root.querySelectorAll('input, select, textarea')).filter(
			(el) => {
				const id = el.getAttribute('id');
				// Either association counts: an explicit label[for], or an implicit
				// wrapping label — both name the control per the HTML spec.
				const hasLabel = id
					? root.querySelector(`label[for="${id}"]`) !== null
					: (el.closest('label')?.textContent?.trim() ?? '') !== '';
				return !hasLabel && !el.getAttribute('aria-label');
			}
		);
		checks.push(
			unlabelledInputs.length === 0
				? { verifier: 'a11y', status: 'ok', label: 'inputs labelled' }
				: { verifier: 'a11y', status: 'fail', label: `${unlabelledInputs.length} unlabelled input(s)` }
		);

		const altless = Array.from(root.querySelectorAll('img')).filter((img) => !img.hasAttribute('alt'));
		checks.push(
			altless.length === 0
				? { verifier: 'a11y', status: 'ok', label: 'images have alt' }
				: { verifier: 'a11y', status: 'fail', label: `${altless.length} image(s) missing alt` }
		);

		return checks;
	}
};
