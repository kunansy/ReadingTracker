export enum MaterialType {
  book = "book",
  article = "article",
  course = "course",
  lecture = "lecture",
  audiobook = "audiobook"
}

export const MaterialTypes = Object.values(MaterialType);

export type MaterialJson = {
  material_id: string;
  index: number;
  title: string;
  authors: string;
  pages: number;
  material_type: MaterialType;
  tags: string | null;
  link: string | null;
  added_at: string;
  is_outlined: boolean;
};

export type MaterialEstimateJson = {
  material: MaterialJson;
  will_be_started: string;
  will_be_completed: string;
  expected_duration: number;
};

export type MinMaxJson = { count: number; date: string };

export type MaterialStatisticsJson = {
  material: MaterialJson;
  started_at: string;
  duration: number;
  lost_time: number;
  total: number;
  min_record: MinMaxJson | null;
  max_record: MinMaxJson | null;
  mean: number;
  notes_count: number;
  remaining_pages: number | null;
  remaining_days: number | null;
  /** Present for completed materials list */
  completed_at?: string | null;
  total_reading_duration: string | null;
  would_be_completed: string | null;
  percent_completed: number;
};

type RepeatingQueueJson = {
  material_id: string;
  title: string;
  pages: number;
  material_type: MaterialType;
  is_outlined: boolean;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  completed_at: string | null;
  last_repeated_at: string | null;
  priority_days: number;
  priority_months: number;
};

export type GetRepeatingQueueResponse = {
  repeating_queue: RepeatingQueueJson[];
};


export type MaterialTagsResponse = {
  tags: string[];
};

export type MaterialAuthorsResponse = {
  authors: string[];
}

export type ParsedMaterialResponse = {
  title: string;
  authors: string;
  type: string;
  link: string;
  duration?: number | null;
};

export type ListCompletedMaterialsResponse = {
  statistics: MaterialStatisticsJson[];
};

