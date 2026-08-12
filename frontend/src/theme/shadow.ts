// Enterprise redesign pass — soft, deep "floating" shadows (navy-tinted rather than flat
// black, per the brief's "soft enterprise shadow" example) instead of the tight default-UI
// shadow every card previously used. `cardHover`/`glass` are new, used by the hover-lift
// utility and the login page's glass card respectively.
export const boxShadow = {
  card: "0 8px 30px rgba(15, 23, 42, 0.07)",
  cardHover: "0 16px 40px rgba(15, 23, 42, 0.12)",
  dropdown: "0 10px 40px rgba(15, 23, 42, 0.14)",
  glass: "0 8px 32px rgba(15, 23, 42, 0.25)",
} as const;
