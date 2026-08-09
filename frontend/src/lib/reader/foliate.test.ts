import { describe, expect, it } from 'vitest';
import { furthestCfi } from './foliate';

const COVER = 'epubcfi(/6/2!/4/2[coverpage]/2)';
const LATER = 'epubcfi(/6/24!/4/2/10/2)';

describe('furthestCfi', () => {
	it('keeps the later location whichever way round it comes', async () => {
		expect(await furthestCfi(COVER, LATER)).toBe(LATER);
		expect(await furthestCfi(LATER, COVER)).toBe(LATER);
	});
	it('falls back to whichever location exists', async () => {
		expect(await furthestCfi(null, COVER)).toBe(COVER);
		expect(await furthestCfi(COVER, null)).toBe(COVER);
		expect(await furthestCfi(null, null)).toBeNull();
	});
	it('compares a range CFI against a point one', async () => {
		expect(await furthestCfi('epubcfi(/6/2!/4/2,/2/1:0,/2/1:8)', LATER)).toBe(LATER);
	});
});
