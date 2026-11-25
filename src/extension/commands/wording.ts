/** "1 subject", "41 subjects": a count with its noun. */
export const plural = (n: number, noun: string): string => `${n} ${noun}${n === 1 ? "" : "s"}`;
