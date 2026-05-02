export enum MaterialType {
  book = "book",
  article = "article",
  course = "course",
  lecture = "lecture",
  audiobook = "audiobook"
}

export const MaterialTypes = Object.values(MaterialType);

type GetMaterialItem = {
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

type MaterialEstimateJson = {
  material: GetMaterialItem;
  will_be_started: string;
  will_be_completed: string;
  expected_duration: number;
};

export type MinMaxJson = { count: number; date: string };

type MaterialStatisticsJson = {
  material: GetMaterialItem;
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

export type ListReadingMaterialsResponse = {
  statistics: MaterialStatisticsJson[];
};

export type ListCompletedMaterialsResponse = {
  statistics: MaterialStatisticsJson[];
};

export type ListMaterialsQueueResponse = {
  estimates: MaterialEstimateJson[];
  mean: Record<string, number>;
};

export type GetMaterialResponse = {
  material: GetMaterialItem;
};

export type ListReadingMaterialsTitlesResponse = {
  items: Record<string, string>;
}

export type GetMaterialCompletionInfoResponse = {
  material_pages: number;
  material_type: MaterialType;
  pages_read: number;
  read_days: number;
}

export type GetMaterialReadingNowResponse = {
  material_id: string;
}

type ListReadingLogsItem = {
  log_id: string;
  material_id: string;
  date: string;
  count: number;
};

export type ListReadingLogsResponse = {
  items: ListReadingLogsItem[];
};

export type ListMaterialsTitlesResponse = {
  items: Record<string, string>;
}

type ListCardsItem = {
  card_id: string;
  note_id: string;
  material_id: string;
  question: string;
  answer: string | null;
  added_at: string;
  note_title: string | null;
  note_content: string;
  note_chapter: string;
  note_page: number;
  material_title: string;
  material_authors: string;
  material_type: MaterialType;
}

export type ListCardsResponse = {
  items: ListCardsItem[];
}

export type SystemMetaResponse = {
  material_id: string | null;
  titles: Record<string, string>;
};

export type SpanSummary = {
  total: number;
  would_be_total: number;
  zero_days: number;
  mean: number;
  median: number;
  max_record: { date: string; amount: number };
  min_record: { date: string; amount: number };
};

type TrackerStatistics = {
  started_at: string;
  finished_at: string;
  duration: number;
  lost_time: number;
  duration_period: string;
  lost_time_period: string;
  lost_time_percent: number;
  mean: number;
  median: number;
  total_materials_completed: number;
  pages_read: Record<string, number>;
  materials_completed: Record<string, number>;
  total_pages_read: number;
  would_be_total: number;
  max_log_record: { count: number; date: string; material_title: string } | null;
  min_log_record: { count: number; date: string; material_title: string } | null;
};

export type SystemSummaryResponse = {
  tracker_statistics: TrackerStatistics;
  reading_trend: SpanSummary;
  notes_trend: SpanSummary;
  completed_materials_trend: SpanSummary;
  repeated_materials_trend: SpanSummary;
  outlined_materials_trend: SpanSummary;
};

export type GraphicResponse = { image: string };

export type BackupResponse = {
  materials_count: number;
  reading_log_count: number;
  statuses_count: number;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  note_repeats_history_count: number;
};

export type RestoreResponse = {
  materials_count: number;
  reading_log_count: number;
  statuses_count: number;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  note_repeats_history_count: number;
};
