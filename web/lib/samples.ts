// Sample reference plates for trying the builder without your own image. Generated with GPT Image 2.5 Sunburst by
// generate/samples.sh; served from public/samples/<id>.jpg (1536 px) with <id>_thumb.jpg (768 px) for the picker.
export interface Sample {
  id: string;
  label: string;
}

export const SAMPLES: Sample[] = [
  { id: "apothecary", label: "Victorian apothecary" },
  { id: "noir", label: "1940s detective office" },
  { id: "diner", label: "Desert diner at night" },
  { id: "arcade", label: "1985 arcade" },
  { id: "jazz", label: "Basement jazz bar" },
  { id: "library", label: "University library" },
  { id: "cabin", label: "Cabin kitchen, winter" },
  { id: "greenhouse", label: "Victorian greenhouse" },
  { id: "garage", label: "Garage workshop" },
  { id: "forge", label: "Blacksmith forge" },
  { id: "subway", label: "Abandoned subway platform" },
  { id: "cargo", label: "Spaceship cargo bay" },
];

export const sampleUrl = (id: string) => `/samples/${id}.jpg`;
export const sampleThumb = (id: string) => `/samples/${id}_thumb.jpg`;

/** The sample as a File, so it goes through the same upload as a dropped image. */
export async function sampleFile(s: Sample): Promise<File> {
  const r = await fetch(sampleUrl(s.id));
  if (!r.ok) throw new Error(`Couldn't load the ${s.label} sample (HTTP ${r.status}).`);
  return new File([await r.blob()], `${s.id}.jpg`, { type: "image/jpeg" });
}
