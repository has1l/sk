import { PET_NAME, PetArt, useSkin } from "./Pet";

/** Предложение посмотреть разбор на дашборде.
 *
 *  Раньше показ начинался сам, сразу после ответа. Это неверно: человек
 *  сначала читает, что ему написали, и только потом решает, идти ли смотреть.
 *  Бежать за ним раньше него — значит перебивать.
 */
export function ShowOffer({ onShow }: { onShow: () => void }) {
  const color = useSkin();
  return (
    <button className="show-offer" onClick={onShow}>
      <PetArt mood="glad" size={1.5} color={color} />
      <span>
        <strong>Показать на дашборде</strong>
        <em>{PET_NAME} пройдёт по нему и объяснит, что откуда</em>
      </span>
    </button>
  );
}
